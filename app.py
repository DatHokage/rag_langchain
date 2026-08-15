"""
app.py — Buoc 6 roadmap: Giao dien Streamlit cho chatbot quy che.

Goi truc tiep RAG chain (in-process) — khong can chay FastAPI rieng.
Chuc nang:
  - Chat multi-turn (giu lich su 3 cap hoi-dap gan nhat, nhu CLI)
  - Hien thi cau tra loi + khung nguon trich dan (Dieu/Khoan/Trang + van ban goc)
  - Sidebar chon model LLM mien phi (tu dong lay danh sach :free tu OpenRouter)
  - Khi loi: nut "Thu lai voi model khac" tu dong chuyen sang model tiep theo
  - Badge hien thi model thuc te tra loi (ke ca khi tu dong fallback)
  - Nut bam goi y cau hoi pho bien
  - Sidebar: trang thai he thong (vector store, API key) + xoa lich su chat

Cach chay:
  streamlit run app.py
"""
from __future__ import annotations

import os
import sys

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Windows console mac dinh cp1252 khong in duoc tieng Viet
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

st.set_page_config(page_title="Chatbot Quy chế", page_icon="🏫", layout="centered")

# ---- Font chu: Be Vietnam Pro (Google Fonts, ho tro tieng Viet day du) ----
st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap"
          rel="stylesheet">
    <style>
      html, body, [class*="css"],
      .stMarkdown, .stText, .stButton, .stChatInput, .stSidebar,
      .stChatMessage, .stAlert, .stCaption, .stExpander,
      h1, h2, h3, h4, h5, h6, p, li, a, blockquote,
      button, input, textarea, label {
        font-family: "Be Vietnam Pro", sans-serif !important;
      }
      /* Giu nguyen icon cua Streamlit (Material Symbols) —
         khong de font Be Vietnam Pro de len, neu khong icon se
         hien thanh chu (vd: "keyboard_double_arrow_left") */
      [data-testid="stIconMaterial"] {
        font-family: "Material Symbols Rounded" !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

VECTORSTORE_DIR = os.getenv("VECTORSTORE_DIR", "vectorstore")

CAU_HOI_GOI_Y = [
    "Người học có những quyền gì theo quy chế?",
    "Sinh viên bị cấm thi trong những trường hợp nào?",
    "Điều kiện xét học bổng khuyến khích học tập là gì?",
    "Có những hình thức kỷ luật nào đối với người học vi phạm?",
    "Quy trình xử lý kỷ luật người học gồm những bước nào?",
]


@st.cache_resource(show_spinner="Đang tải mô hình (embedding + vector store)...")
def warmup() -> tuple[bool, str]:
    """Tai chain + vectorstore 1 lan cho ca phien (cau hoi dau khong phai cho)."""
    try:
        from src.rag.chain import build_chain
        build_chain()
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _ref_label(s: dict) -> str:
    """Nhan ngan gon cho 1 nguon: Dieu X, Khoan Y, tr.~Z."""
    parts = [x for x in (s.get("dieu"), s.get("khoan")) if x]
    if s.get("so_trang"):
        parts.append(f"tr.~{s['so_trang']}")
    return ", ".join(parts) if parts else "Nguồn khác"


def _provider_label(provider: str, model: str = "") -> str:
    """Nhan badge: provider + model thuc te tra loi (ke ca khi fallback)."""
    if provider == "openrouter":
        name = "⚡ OpenRouter"
    elif provider == "gemini":
        name = "✨ Gemini"
    else:
        name = provider
    return f"{name} · `{model}`" if model else name


def render_sources(sources: list[dict]) -> None:
    """Hien thi cac nguon trich dan trong expander."""
    if not sources:
        return
    with st.expander(f"📎 {len(sources)} nguồn trích dẫn", expanded=False):
        for i, s in enumerate(sources, 1):
            st.markdown(f"**{i}. {_ref_label(s)}**")
            if s.get("muc"):
                st.caption(s["muc"])
            if s.get("text"):
                st.markdown(
                    f"<div style='border-left:3px solid #c9d1d9; "
                    f"padding:6px 12px; margin:4px 0 12px; "
                    f"font-size:0.9em; color:#555'>{s['text'][:600]}"
                    f"{'…' if len(s['text']) > 600 else ''}</div>",
                    unsafe_allow_html=True,
                )


def main() -> None:
    st.title("🏫 Chatbot Quy chế Trường học")
    st.caption("Tra cứu quy chế — trả lời tiếng Việt kèm trích dẫn "
               "Điều / Khoản / Trang")

    from src.rag import models as model_registry

    # ---- Trang thai he thong + chon model (sidebar) ----
    with st.sidebar:
        st.header("⚙️ Hệ thống")
        vs_ok = os.path.isdir(VECTORSTORE_DIR)
        st.markdown(f"Vector store: {'🟢 sẵn sàng' if vs_ok else '🔴 chưa build'}")
        or_ok = model_registry.openrouter_available()
        gemini_ok = model_registry.gemini_available()
        st.markdown(f"OpenRouter API key (chính): "
                    f"{'🟢' if or_ok else '⚪ chưa có'}")
        st.markdown(f"Gemini API key (dự phòng): "
                    f"{'🟢' if gemini_ok else '⚪ chưa có'}")

        # Danh sach model mien phi kha dung (OpenRouter :free + Gemini)
        model_specs = model_registry.list_available_models() if \
            (or_ok or gemini_ok) else []
        model_labels = [s["label"] for s in model_specs]

        st.divider()
        st.markdown("**🤖 Mô hình LLM** (miễn phí)")
        default_sel = model_registry.default_selection()
        auto_label = "🔄 Tự động (model tốt nhất)"
        if default_sel:
            auto_label += f" — hiện: `{default_sel['model']}`"
        options = [auto_label] + model_labels
        # selectbox tra ve GIA TRI dang chon (label), khong phai index
        selection = st.selectbox(
            "Chọn model — lỗi sẽ tự chuyển sang model khác",
            options,
            index=0,
            disabled=not options[1:],
            help="Mỗi câu hỏi thử lần lượt từ model được chọn; model nào "
                 "trả lời được thì dừng (miễn phí nên có thể bị giới hạn "
                 "tần suất, đặc biệt Gemini).",
        )
        chosen = None
        if selection in model_labels and model_specs:
            chosen = model_specs[model_labels.index(selection)]

        if st.button("🔄 Làm mới danh sách model", use_container_width=True,
                     help="Gọi lại API OpenRouter để lấy danh sách model :free mới nhất"):
            model_registry.get_openrouter_free_models(refresh=True)
            st.rerun()

        st.divider()
        if st.button("🗑️ Xoá lịch sử chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.history = []
            st.rerun()

    if not (vs_ok and (gemini_ok or or_ok)):
        if not vs_ok:
            st.warning("Chưa có vector store. Chạy:\n\n"
                       "`python -m src.ingestion.build_index`")
        else:
            st.warning("Chưa có API key. Copy `.env.example` thành `.env` "
                       "và điền `OPENROUTER_API_KEY` (hoặc `GOOGLE_API_KEY`).")
        return

    ok, err = warmup()
    if not ok:
        st.error(f"Không khởi động được RAG chain: {err}")
        return

    # ---- Khoi tao session state ----
    if "messages" not in st.session_state:
        st.session_state.messages = []   # de render: {role, content, sources, provider, model}
    if "history" not in st.session_state:
        st.session_state.history = []    # de gui chain: list[BaseMessage]

    # ---- Render lich su chat ----
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                render_sources(msg["sources"])
            if msg.get("provider"):
                st.caption(_provider_label(msg["provider"], msg.get("model", "")))

    # ---- Nut goi y khi chua co tin nhan nao ----
    if not st.session_state.messages:
        st.markdown("**Thử hỏi:**")
        cols = st.columns(2)
        for i, q in enumerate(CAU_HOI_GOI_Y):
            if cols[i % 2].button(q, key=f"sug_{i}", use_container_width=True):
                st.session_state.pending = q
                st.rerun()

    question = st.session_state.pop("pending", None) or \
        st.chat_input("Hỏi về quy chế... (VD: Sinh viên bị cấm thi khi nào?)")

    if question:
        # Cau hoi moi -> bo thong bao loi cu (neu co)
        st.session_state.pop("retry_ctx", None)
        # Khi bam nut "Thu lai": cau hoi da co san trong messages -> chi ve,
        # khong them trung
        if st.session_state.pop("retry_no_dup", False) \
                and st.session_state.messages \
                and st.session_state.messages[-1].get("content") == question:
            pass
        else:
            st.session_state.messages.append(
                {"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        from langchain_core.messages import AIMessage, HumanMessage
        from src.rag.chain import ask

        # Model duoc chon: nut retry chuyen sang (forced) > dropdown > tu dong
        forced = st.session_state.pop("forced_model", None)
        if forced and forced in model_labels:
            sel = model_specs[model_labels.index(forced)]
        else:
            sel = chosen   # None = che do tu dong

        try:
            with st.chat_message("assistant"):
                with st.spinner("Đang tra cứu quy chế..."):
                    r = ask(question, chat_history=st.session_state.history,
                            provider=sel["provider"] if sel else "",
                            model=sel["model"] if sel else "")
                st.markdown(r["answer"])
                render_sources(r["sources"])
                st.caption(_provider_label(r["provider"], r.get("model", "")))
            st.session_state.messages.append({
                "role": "assistant", "content": r["answer"],
                "sources": r["sources"], "provider": r["provider"],
                "model": r.get("model", ""),
            })
            # Cap nhat lich su cho chain (giu 3 cap hoi-dap, giong CLI)
            st.session_state.history.extend([
                HumanMessage(content=question),
                AIMessage(content=r["answer"]),
            ])
            st.session_state.history = st.session_state.history[-6:]
        except Exception as e:
            msg = str(e)
            if "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
                err_text = ("Tất cả model đang bị giới hạn tần suất. "
                            "Chờ một lát rồi thử lại, hoặc chọn model khác "
                            "ở thanh bên trái.")
            else:
                err_text = f"Lỗi: {type(e).__name__}: {msg[:300]}"
            # Model tiep theo trong danh sach de nut "Thu lai" chuyen sang
            next_label = None
            if model_labels:
                cur = sel["label"] if sel else None
                try:
                    i = model_labels.index(cur) if cur else -1
                except ValueError:
                    i = -1
                next_label = model_labels[(i + 1) % len(model_labels)]
            # Luu trang thai loi -> rerun de nut "Thu lai" duoc ve ra
            # (Streamlit chi nhan click cua button duoc ve trong run do)
            st.session_state.retry_ctx = {
                "question": question, "next_label": next_label,
                "error": err_text,
            }
            st.rerun()

    # ---- Khoi bao loi + nut thu lai voi model khac ----
    # Ve NGOAI khoi "if question:" vi nut phai ton tai trong moi run thi
    # click cua user moi co tac dung (chat_input chi co gia tri 1 run duy nhat)
    retry_ctx = st.session_state.get("retry_ctx")
    if retry_ctx:
        st.error(retry_ctx["error"])
        hint = f" (chuyển sang {retry_ctx['next_label']})" \
            if retry_ctx.get("next_label") else ""
        if st.button(f"🔄 Thử lại với model khác{hint}",
                     use_container_width=True, key="retry_btn"):
            st.session_state.pending = retry_ctx["question"]
            if retry_ctx.get("next_label"):
                st.session_state.forced_model = retry_ctx["next_label"]
            st.session_state.retry_no_dup = True
            st.rerun()


if __name__ == "__main__":
    main()
