"""
run_eval.py — Buoc 7 roadmap: Danh gia chatbot bang bo cau hoi mau.

Luong danh gia (2 lop, khong can LLM-as-judge nen chay duoc offline 1 phan):

1. RETRIEVAL (khong can API key):
   - Voi moi cau hoi, lay top-k chunks tu retriever.
   - Do "hit": chunk tra ve co chua dieu/quy che ky vong
     (expected_dieu / expected_muc) khong?
   - Chi so: retrieval hit-rate %.

2. ANSWER (can API key — chi chay khi co --llm):
   - Chay cau hoi qua RAG chain, in cau tra loi + nguon de DANH GIA THU CONG.
   - Cau co note "REFUSE": kiem tra chatbot co tu choi dung khong.

Cach chay:
  python -m src.eval.run_eval                 # chi danh gia retrieval
  python -m src.eval.run_eval --llm           # danh gia ca cau tra loi (ton quota)
  python -m src.eval.run_eval --llm -k 3      # chi chay 3 cau dau
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

# Windows console mac dinh cp1252 khong in duoc tieng Viet
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

load_dotenv()

QUESTIONS_FILE = Path(__file__).resolve().parent.parent.parent / \
    "tests" / "sample_questions.json"

REFUSE_PATTERN = re.compile(
    r"khong tim thay thong tin|không tìm thấy thông tin", re.I)


def load_questions() -> list[dict]:
    data = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    return data


def _hit(q: dict, chunks_text: list[str], metadatas: list[dict]) -> bool:
    """Chunk tra ve co khop voi dieu/quy che ky vong khong?"""
    expected_dieu = q.get("expected_dieu", "")
    expected_muc = q.get("expected_muc", "")
    if not expected_dieu and not expected_muc:
        # Cau ngoai pham vi: khong danh gia retrieval
        return True
    for text, m in zip(chunks_text, metadatas):
        dieu_ok = (not expected_dieu
                   or expected_dieu.lower() in m.get("dieu", "").lower())
        muc_ok = (not expected_muc
                  or expected_muc.lower() in (m.get("muc", "") + " "
                                              + m.get("trich", "")
                                              + " " + text[:400]).lower())
        if dieu_ok and muc_ok:
            return True
    return False


def eval_retrieval(questions: list[dict], top_k: int = 5,
                   limit: int | None = None) -> None:
    """Danh gia chat luong retrieval: hit-rate theo expected_dieu/expected_muc."""
    from src.rag.retriever import get_retriever

    retriever = get_retriever(top_k=top_k)
    qs = questions[:limit] if limit else questions
    hits, scored = 0, 0

    print(f"=== DANH GIA RETRIEVAL (top-{top_k}, {len(qs)} cau) ===\n")
    for i, q in enumerate(qs, 1):
        t0 = time.time()
        docs = retriever.invoke(q["question"])
        dt = time.time() - t0
        ok = _hit(q, [d.page_content for d in docs],
                  [d.metadata for d in docs])
        if q.get("expected_dieu") or q.get("expected_muc"):
            scored += 1
            hits += ok
        mark = "✓" if ok else "✗"
        print(f"{mark} [{i:2d}] {q['question']}")
        if not ok:
            print(f"      ky vong: {q.get('expected_dieu','')} / "
                  f"{q.get('expected_muc','')[:50]}")
            for d in docs[:2]:
                print(f"      -> nhan: {d.metadata.get('dieu','')} | "
                      f"{d.metadata.get('muc','')[:45]}")
        print(f"      ({dt:.2f}s)")
    if scored:
        print(f"\nKET QUA: {hits}/{scored} cau hit ({hits/scored:.0%})")
    else:
        print("\nKhong co cau nao de danh gia")


def eval_answer(questions: list[dict], limit: int | None = None,
                top_k: int = 5) -> None:
    """Chay qua RAG chain, in ket qua de danh gia thu cong."""
    from src.rag.chain import ask

    qs = questions[:limit] if limit else questions
    n_refuse_expected = 0
    n_refuse_ok = 0

    print(f"=== DANH GIA CAU TRA LOI (LLM, {len(qs)} cau) ===\n")
    for i, q in enumerate(qs, 1):
        print(f"--- [{i:2d}] {q['question']}")
        try:
            r = ask(q["question"], top_k=top_k)
        except Exception as e:
            print(f"    [LOI] {type(e).__name__}: {e}\n")
            continue
        print(f"    ({r['provider']}) {r['answer'][:400]}")
        srcs = ", ".join(s["dieu"] for s in r["sources"] if s["dieu"])
        if srcs:
            print(f"    Nguon: {srcs}")

        if q.get("expected_answer") == "REFUSE":
            n_refuse_expected += 1
            if REFUSE_PATTERN.search(r["answer"]):
                n_refuse_ok += 1
                print("    [TU CHOI DUNG]")
            else:
                print("    [CANH BAO] Cho rang tu choi nhung tra loi co noi dung")
        print()
    if n_refuse_expected:
        print(f"TU CHOI NGOAI PHAM VI: {n_refuse_ok}/{n_refuse_expected} dung")


def main() -> None:
    ap = argparse.ArgumentParser(description="Danh gia chatbot quy che")
    ap.add_argument("--llm", action="store_true",
                    help="Chay ca danh gia cau tra loi (can API key)")
    ap.add_argument("-k", "--limit", type=int, default=None,
                    help="Chi chay N cau dau tien")
    from src.rag.retriever import RETRIEVER_TOP_K

    ap.add_argument("--top-k", type=int, default=RETRIEVER_TOP_K)
    args = ap.parse_args()

    questions = load_questions()
    print(f"Bo cau hoi: {len(questions)} cau\n")

    eval_retrieval(questions, top_k=args.top_k, limit=args.limit)
    if args.llm:
        print()
        eval_answer(questions, limit=args.limit, top_k=args.top_k)
    else:
        print("\n(Bo qua danh gia cau tra loi — chay voi --llm de danh gia)")


if __name__ == "__main__":
    main()
