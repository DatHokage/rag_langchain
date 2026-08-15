# 🏫 Chatbot Quy chế Trường học — RAG với LangChain

Chatbot hỏi-đáp tra cứu **Quy chế trường học** (~160 trang), trả lời bằng tiếng Việt
kèm trích dẫn **Điều / Khoản / Trang**, dùng kỹ thuật RAG (Retrieval-Augmented Generation).

> 📄 Đặc tả đầy đủ: xem [`project.md`](project.md)

## Kiến trúc

```
PDF/DOCX quy chế
  → loader → chunker (theo Điều/Khoản) → embedding local
  → ChromaDB → retriever (top-k + MMR)
  → LLM (Gemini, fallback Groq) → câu trả lời + trích dẫn
  → FastAPI /chat
```

**Điểm nổi bật:**
- ✅ Embedding chạy **local 100%** (vietnamese-bi-encoder) — không tốn phí, không lo quota
- ✅ LLM dùng **free tier**: Gemini (chính) + Groq (dự phòng tự động khi hết quota)
- ✅ Chống ảo giác: chỉ trả lời theo ngữ cảnh, từ chối khi ngoài phạm vi quy chế

## Cài đặt

### 1. Clone & tạo môi trường ảo

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Cấu hình API keys

```powershell
copy .env.example .env
```

Mở `.env` và điền:

| Biến | Lấy key ở đâu | Ghi chú |
|---|---|---|
| `GOOGLE_API_KEY` | https://aistudio.google.com/apikey | Miễn phí, **bắt buộc** |
| `GROQ_API_KEY` | https://console.groq.com/keys | Miễn phí, khuyến nghị (fallback) |

> 🔑 **Không commit `.env` vào Git** — đã có trong `.gitignore`.

### 3. Đặt tài liệu quy chế

Copy file PDF/DOCX quy chế vào thư mục `data/raw/` (VD: `data/raw/quy_che.pdf`).

### 4. Build index (không cần API key)

```powershell
python -m src.ingestion.build_index
```

Lần đầu sẽ tải embedding model (~1GB) về cache. Khi quy chế cập nhật, chỉ cần
đặt file mới vào `data/raw/` và chạy lại lệnh trên.

### 5. Chạy chatbot CLI (test nhanh)

```powershell
python -m src.rag.chain
```

### 6. Giao diện web Streamlit (khuyến nghị để demo)

```powershell
streamlit run app.py
```

Trình duyệt tự mở tại `http://localhost:8001` — chat trực tiếp, xem nguồn
trích dẫn (Điều / Khoản / Trang + văn bản gốc), hỏi tiếp theo ngữ cảnh.

### 7. Chạy API server

```powershell
uvicorn src.api.main:app --reload --port 8000
```

Test thử:

```powershell
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{\"question\": \"Sinh viên bị cấm thi trong trường hợp nào?\", \"session_id\": \"test\"}'
```

### 8. Đánh giá chất lượng

```powershell
# Chỉ đánh giá retrieval (không tốn API key):
python -m src.eval.run_eval

# Đánh giá cả câu trả lời LLM (tốn quota free tier):
python -m src.eval.run_eval --llm
```

Bộ câu hỏi mẫu: `tests/sample_questions.json` (29 câu, gồm 2 câu ngoài phạm vi
để kiểm tra chatbot có biết từ chối). Kết quả retrieval in ra dạng ✓/✗ — phần
câu trả lời đánh giá thủ công. Hit-rate retrieval hiện tại: **26/27 (96%)**.

## Cấu trúc thư mục

```
rag_langchain/
├── data/
│   ├── raw/                 # 📥 Đặt file quy chế gốc vào đây (PDF/DOCX)
│   └── processed/           # Chunks đã parse (JSON)
├── src/
│   ├── ingestion/
│   │   ├── loader.py        # Đọc & parse PDF/DOCX, nhận diện Chương/Điều/Khoản
│   │   ├── chunker.py       # Chia chunk theo Điều (300-500 tokens, có overlap)
│   │   └── build_index.py   # Build ChromaDB index (chạy offline)
│   ├── rag/
│   │   ├── retriever.py     # Similarity search top-k + MMR
│   │   ├── prompts.py       # Prompt template (chống ảo giác + trích dẫn)
│   │   └── chain.py         # LCEL chain, fallback Gemini → Groq
│   ├── api/
│   │   └── main.py          # FastAPI: /chat, /health
│   └── eval/
│       └── run_eval.py      # Đánh giá retrieval + câu trả lời (27 câu mẫu)
├── app.py                   # Giao diện Streamlit (chạy: streamlit run app.py)
├── tests/                   # Bộ câu hỏi mẫu (sample_questions.json)
├── logs/                    # Log câu hỏi/trả lời dạng JSONL (gitignore)
├── vectorstore/             # ChromaDB persist (gitignore, build lại được)
├── .env.example             # Mẫu cấu hình — copy thành .env
├── requirements.txt
└── project.md               # 📄 Đặc tả đầy đủ của dự án
```

## Roadmap triển khai

- [x] **Bước 1**: Setup skeleton, requirements.txt, .env.example
- [x] **Bước 2**: Loader + chunker (parse PDF/DOCX theo Chương/Điều/Khoản)
- [x] **Bước 3**: Build index (embedding local + ChromaDB) + test retrieval
- [x] **Bước 4**: Prompt template + RAG chain (fallback Gemini → Groq)
- [x] **Bước 5**: API FastAPI (`/chat`, `/health`)
- [x] **Bước 6**: Giao diện Streamlit (`app.py` — chat + nguồn trích dẫn)
- [x] **Bước 7**: Bộ câu hỏi mẫu + đánh giá
- [x] **Bước 8**: Hoàn thiện README

## Tech stack

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| Framework | LangChain (LCEL) | Chuẩn hệ sinh thái RAG |
| Vector store | ChromaDB (local) | Miễn phí, đủ cho 160 trang |
| Embedding | `bkai-foundation-models/vietnamese-bi-encoder` (local) | Tối ưu tiếng Việt, miễn phí 100% |
| LLM chính | Gemini 3.6 Flash (free tier) | Tiếng Việt tốt, quota rộng |
| LLM dự phòng | Groq Llama 3.3 70B (free tier) | Rất nhanh, tự fallback |
| API | FastAPI + Uvicorn | Async, dễ deploy |

## Ghi chú vận hành

- **Free tier có giới hạn request** — với API key Google tạo mới (2026),
  hạn mức chỉ **~20 request/ngày cho mỗi model Gemini**. Chạy hết bộ eval
  (`--llm`) sẽ tốn sạch quota trong ngày. Cách xử lý khi cần chạy nhiều:
  - Tạo thêm key khác (mỗi key một hạn mức riêng), hoặc
  - Lấy thêm `GROQ_API_KEY` để hệ thống tự fallback, hoặc
  - Chia nhỏ: `python -m src.eval.run_eval --llm -k 5` mỗi ngày một ít.
- **Model**: cấu hình mặc định `gemini-3.6-flash` — các model cũ
  (`gemini-2.0-flash`, `gemini-2.5-flash`) đã bị Google ngừng hỗ trợ cho
  key mới. Nếu lỗi 404 model, kiểm tra danh sách model dùng được tại
  https://aistudio.google.com/apikey hoặc API `/v1beta/models`.
- **Log**: câu hỏi + trả lời được ghi ra `logs/` để đánh giá và cải thiện.
- **Re-index**: quy chế thay đổi → đặt file mới vào `data/raw/` → chạy lại
  `python -m src.ingestion.build_index` (không cần fine-tune, không cần code lại).
