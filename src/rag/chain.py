"""
chain.py — Buoc 4 roadmap: RAG chain voi fallback qua nhieu model mien phi.

Kien truc LCEL:
    retriever -> (context, question, chat_history) -> prompt -> llm -> parser

Co che fallback (muc 10 project.md):
    1. Thu goi model duoc chon (web/CLI truyen vao, mac dinh theo .env)
    2. Neu loi (rate-limit/het quota/...) -> tu dong chuan sang cac model
       mien phi khac trong registry (xem src/rag/models.py), Gemini free
       tier la chot chan cuoi cung
    3. Provider + model nao thuc te phuc vu duoc ghi trong ket qua + log

Dau ra ham ask():
    { "answer": str, "sources": [ {phan, chuong, muc, dieu, khoan, so_trang,
                                    ten_dieu, text} ],
      "provider": "gemini|openrouter", "model": <model_id> }

Chay CLI test:  python -m src.rag.chain
"""
from __future__ import annotations

import logging
import os
import sys
from operator import itemgetter

from dotenv import load_dotenv

load_dotenv()

# Windows console mac dinh cp1252 khong in duoc tieng Viet
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import (Runnable, RunnableLambda, RunnableParallel,
                                      RunnablePassthrough)

from src.rag import models as model_registry
from src.rag.prompts import QA_PROMPT
from src.rag.retriever import RETRIEVER_TOP_K, get_retriever

logger = logging.getLogger(__name__)


class FallbackLLM(Runnable):
    """Boc nhieu LLM: goi lan luot tung model cho den khi co model tra loi.

    Thu tu: model duoc chon (web/CLI) -> cac model mien phi khac trong
    registry -> Gemini free tier. Provider + model phuc vu luon duoc
    log + tra ve.
    """

    def __init__(self, llms: list[tuple[str, str, object]]):
        # moi phan tu: (provider, model_id, chat_model)
        self.llms = [x for x in llms if x[2] is not None]
        self.last_provider = ""
        self.last_model = ""
        if not self.llms:
            raise RuntimeError(
                "Chua co API key nao: dien OPENROUTER_API_KEY hoac GOOGLE_API_KEY "
                "trong .env (xem .env.example)"
            )

    def invoke(self, input, config=None, **kwargs):
        errors: list[str] = []
        for i, (provider, model_id, llm) in enumerate(self.llms):
            try:
                result = llm.invoke(input, config=config, **kwargs)
                self.last_provider = provider
                self.last_model = model_id
                if i > 0:
                    logger.info("Model phuc vu: %s (%s)", model_id, provider)
                return result
            except Exception as e:
                errors.append(f"{provider}/{model_id}: "
                              f"{type(e).__name__} {str(e)[:140]}")
                if i + 1 < len(self.llms):
                    next_id = self.llms[i + 1][1]
                    logger.warning("Model %s loi (%s: %s) -> chuyen sang %s",
                                   model_id, type(e).__name__, str(e)[:160],
                                   next_id)
        raise RuntimeError("Tat ca model deu loi:\n  - " + "\n  - ".join(errors))


def _build_fallback_chain(selection: dict | None) -> list[tuple[str, str, object]]:
    """Xep danh sach (provider, model_id, llm) theo thu tu fallback.

    selection = {"provider", "model"} — model duoc chon dung dau;
    selection = None — bat dau tu model mac dinh trong .env.
    """
    ordered: list[tuple[str, str]] = []
    if selection:
        ordered.append((selection["provider"], selection["model"]))
    for spec in model_registry.list_available_models():
        if (spec["provider"], spec["model"]) not in ordered:
            ordered.append((spec["provider"], spec["model"]))

    return [(p, m, model_registry.create_llm(p, m)) for p, m in ordered]


_llm_cache: dict[tuple | None, FallbackLLM] = {}


def get_llm(provider: str = "", model: str = "") -> FallbackLLM:
    """Tra ve LLM singleton theo lua chon (provider, model).

    Goi khong tham so -> lua chon mac dinh theo .env.
    """
    key = (provider, model) if (provider and model) else None
    llm = _llm_cache.get(key)
    if llm is None:
        selection = {"provider": provider, "model": model} if key else None
        llm = FallbackLLM(_build_fallback_chain(selection))
        _llm_cache[key] = llm
    return llm


def format_context(docs) -> str:
    """Ghep cac Document thanh ngu canh cho prompt (header da co san trong chunk)."""
    return "\n\n".join(f"[Đoạn {i}]\n{d.page_content}"
                       for i, d in enumerate(docs, 1))


def format_sources(docs) -> list[dict]:
    """Dinh dang sources tu metadata Document (loai trung lap)."""
    sources, seen = [], set()
    for d in docs:
        m = d.metadata
        key = (m.get("muc", ""), m.get("dieu", ""), m.get("khoan", ""),
               d.page_content[:60])
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            "phan": m.get("phan", ""),
            "chuong": m.get("chuong", ""),
            "chuong_con": m.get("chuong_con", ""),
            "muc": m.get("muc", ""),
            "trich": m.get("trich", ""),
            "dieu": m.get("dieu", ""),
            "ten_dieu": m.get("ten_dieu", ""),
            "khoan": m.get("khoan", ""),
            "so_trang": m.get("so_trang", 0),
            "nguon": m.get("nguon", ""),
            "text": d.page_content,
        })
    return sources


def build_chain(top_k: int = RETRIEVER_TOP_K, use_mmr: bool = True,
                llm: FallbackLLM | None = None):
    """RAG chain LCEL: retrieve -> augment -> generate -> parse.

    Input:  {"question": str, "chat_history": list[BaseMessage]}
    Output: {"answer": str, "docs": list[Document]}
    """
    retriever = get_retriever(top_k=top_k, use_mmr=use_mmr)
    if llm is None:
        llm = get_llm()

    prep = RunnablePassthrough.assign(
        docs=RunnableLambda(itemgetter("question")) | retriever)

    fanout = RunnableParallel(
        context=RunnableLambda(itemgetter("docs")) | format_context,
        question=itemgetter("question"),
        chat_history=itemgetter("chat_history"),
        docs=itemgetter("docs"),
    )

    return (
        prep
        | fanout
        | RunnableParallel(
            answer=QA_PROMPT | llm | StrOutputParser(),
            docs=itemgetter("docs"),
        )
    )


_chain_singleton = None


def ask(question: str, chat_history: list[BaseMessage] | None = None,
        top_k: int = RETRIEVER_TOP_K, use_mmr: bool = True,
        provider: str = "", model: str = "") -> dict:
    """Hoi 1 cau, tra ve {answer, sources, provider, model}.

    provider/model (tuy chon): ep dung model do truoc; cac model mien phi
    con lai van la fallback khi no loi. Bo trong -> model mac dinh theo .env.
    """
    global _chain_singleton
    llm_key = (provider, model) if (provider and model) else None
    if (_chain_singleton is None
            or _chain_singleton[0] != (top_k, use_mmr, llm_key)):
        llm = get_llm(provider, model)
        _chain_singleton = ((top_k, use_mmr, llm_key),
                            build_chain(top_k, use_mmr, llm=llm))
    (key, chain) = _chain_singleton
    llm = get_llm(*key[2]) if key[2] else get_llm()

    result = chain.invoke({"question": question,
                           "chat_history": chat_history or []})
    return {
        "answer": result["answer"],
        "sources": format_sources(result["docs"]),
        "provider": llm.last_provider,
        "model": llm.last_model,
    }


def _print_sources(sources: list[dict]) -> None:
    for s in sources:
        ref = ", ".join(x for x in (s["dieu"], s["khoan"],
                                    f"tr.~{s['so_trang']}" if s["so_trang"] else "")
                        if x)
        muc = s["muc"][:70] if s["muc"] else ""
        print(f"   • {ref} | {muc}")


def cli() -> None:
    """Chat CLI de test nhanh (multi-turn)."""
    print("=" * 60)
    print("CHATBOT QUY CHE — go 'exit' de thoat")
    print("=" * 60)
    history: list[BaseMessage] = []
    while True:
        try:
            q = input("\nBạn> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q.lower() in ("exit", "quit", "thoat"):
            break
        try:
            r = ask(q, chat_history=history)
        except Exception as e:
            print(f"[LOI] {type(e).__name__}: {e}")
            continue
        print(f"\nBot ({r['provider']}/{r.get('model', '?')})> {r['answer']}")
        if r["sources"]:
            print("\nNguồn trích dẫn:")
            _print_sources(r["sources"])
        history.append(HumanMessage(content=q))
        history.append(AIMessage(content=r["answer"]))
        history = history[-6:]   # giu 3 cap hoi-dap gan nhat


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli()
