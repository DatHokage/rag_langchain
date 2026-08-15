"""
main.py — Buoc 5 roadmap: FastAPI endpoints.

Endpoints:
  POST /chat   { question, session_id? } -> { answer, sources, provider, session_id }
  GET  /health -> trang thai vector store + model + API keys

Chuc nang:
- Quan ly session (chat_history) theo session_id — in-memory dict, gioi han
  200 session (LRU) de khong tran RAM.
- Log cau hoi + cau tra loi ra logs/chat_log.jsonl de phuc vu danh gia (muc 10).
- Chain + vectorstore duoc load 1 lan khi server khoi dong (lifespan)
  -> cau hoi dau tien khong phai cho tai model.

Cach chay:
  uvicorn src.api.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from collections import OrderedDict

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

load_dotenv()

# Windows console mac dinh cp1252 khong in duoc tieng Viet
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.rag import chain as rag_chain

logger = logging.getLogger("api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "chat_log.jsonl"
MAX_SESSIONS = 200

# session_id -> list[BaseMessage] (lich su hoi thoai, gioi han 6 message)
_sessions: "OrderedDict[str, list[BaseMessage]]" = OrderedDict()


def _log_exchange(session_id: str, question: str, result: dict) -> None:
    """Ghi log JSONL: 1 dong cho moi cap hoi-dap (phuc vu danh gia)."""
    try:
        LOG_DIR.mkdir(exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "question": question,
            "answer": result.get("answer", ""),
            "provider": result.get("provider", ""),
            "sources": [{k: v for k, v in s.items() if k != "text"}
                        for s in result.get("sources", [])],
        }
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("Log loi (khong chan request): %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khoi dong 1 lan khi server chay: load chain + vectorstore + LLM."""
    try:
        rag_chain.build_chain()   # warm-up: tai embedding model, mo Chroma, tao LLM
        logger.info("RAG chain san sang")
    except Exception as e:
        # Khong chan server — /chat se bao loi ro rang hon
        logger.error("Khoi dong RAG chain that bai: %s", e)
    yield


app = FastAPI(title="Chatbot Quy che Truong hoc",
              description="RAG tra cuu quy che — tra loi tieng Viet kem trich dan",
              version="1.0.0", lifespan=lifespan)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default="default", max_length=200)
    # Tuy chon: ep dung 1 model (vd "openai/gpt-oss-20b:free" hoac
    # provider="gemini", model="gemini-3.6-flash"). Bo trong -> mac dinh .env.
    provider: str = Field(default="", max_length=50)
    model: str = Field(default="", max_length=200)


class SourceOut(BaseModel):
    phan: str = ""
    chuong: str = ""
    chuong_con: str = ""
    muc: str = ""
    trich: str = ""
    dieu: str = ""
    ten_dieu: str = ""
    khoan: str = ""
    so_trang: int = 0
    nguon: str = ""
    text: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    provider: str
    model: str = ""
    session_id: str


@app.get("/health")
def health() -> dict:
    vs_dir = os.getenv("VECTORSTORE_DIR", "vectorstore")
    from src.rag import models as model_registry
    return {
        "status": "ok",
        "vectorstore": {
            "dir": vs_dir,
            "exists": os.path.isdir(vs_dir),
        },
        "embedding_model": os.getenv(
            "EMBEDDING_MODEL", "bkai-foundation-models/vietnamese-bi-encoder"),
        "llm": {
            "default": model_registry.default_selection().get("model", ""),
            "free_models": model_registry.get_openrouter_free_models(),
            "gemini_model": model_registry.gemini_model_id(),
            "gemini_key_set": model_registry.gemini_available(),
            "openrouter_key_set": model_registry.openrouter_available(),
        },
        "sessions": len(_sessions),
    }


@app.get("/models")
def models() -> dict:
    """Danh sach model mien phi kha dung cho web/CLI lua chon."""
    from src.rag import models as model_registry
    return {"models": model_registry.list_available_models(),
            "default": model_registry.default_selection()}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    if not os.path.isdir(os.getenv("VECTORSTORE_DIR", "vectorstore")):
        raise HTTPException(503, "Chua co vector store — chay: "
                                 "python -m src.ingestion.build_index")

    history = _sessions.get(req.session_id, [])
    try:
        result = rag_chain.ask(req.question, chat_history=history,
                               provider=req.provider, model=req.model)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        logger.exception("Chat loi")
        raise HTTPException(500, f"Loi xu ly cau hoi: {e}")

    # Cap nhat lich su (gioi han 6 message ~ 3 vong hoi dap)
    history.extend([HumanMessage(content=req.question),
                    AIMessage(content=result["answer"])])
    _sessions[req.session_id] = history[-6:]
    _sessions.move_to_end(req.session_id)
    while len(_sessions) > MAX_SESSIONS:
        _sessions.popitem(last=False)

    _log_exchange(req.session_id, req.question, result)

    return ChatResponse(answer=result["answer"],
                        sources=[SourceOut(**s) for s in result["sources"]],
                        provider=result["provider"],
                        model=result.get("model", ""),
                        session_id=req.session_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=True)
