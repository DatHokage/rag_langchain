# Chatbot Quy chế Trường học — RAG với LangChain

## 1. Tổng quan

Xây dựng một chatbot hỏi-đáp (Q&A) dựa trên kỹ thuật RAG (Retrieval-Augmented
Generation), giúp học sinh/sinh viên/cán bộ tra cứu nhanh nội dung trong bộ
**Quy chế trường học** (tài liệu PDF/Word, khoảng **160 trang**). Chatbot trả
lời bằng tiếng Việt, dựa hoàn toàn trên nội dung quy chế, có trích dẫn điều/
khoản/trang nguồn để người dùng có thể đối chiếu.

## 2. Mục tiêu

- Trả lời chính xác, đúng ngữ cảnh, hạn chế tối đa "ảo giác" (hallucination).
- Luôn trích dẫn nguồn (số điều, chương, trang) trong câu trả lời.
- Từ chối trả lời khi câu hỏi nằm ngoài phạm vi quy chế, thay vì bịa thông tin.
- Tốc độ phản hồi hợp lý (mục tiêu < 5s/câu hỏi).
- Dễ cập nhật khi quy chế được sửa đổi (không phải fine-tune lại model).

## 3. Phạm vi dữ liệu

- Nguồn: 1 (hoặc vài) file PDF/Word quy chế trường học, ~160 trang.
- Nội dung có cấu trúc phân cấp: Chương → Điều → Khoản → Điểm.
- Có thể chứa bảng biểu (VD: khung điểm rèn luyện, khung xử lý kỷ luật).

## 4. Kiến trúc hệ thống

```
[Tài liệu quy chế (PDF/DOCX)]
        │
        ▼
  Ingestion Pipeline
  - Load & parse (giữ cấu trúc chương/điều)
  - Chunking (theo điều/khoản, có overlap)
  - Embedding
        │
        ▼
   Vector Store (Chroma/FAISS)
        │
        ▼
   Retriever (similarity + rerank)
        │
        ▼
   LLM (qua LangChain) + Prompt template
   (RAG chain: retrieve → augment → generate)
        │
        ▼
   Câu trả lời + trích dẫn nguồn
        │
        ▼
   Giao diện (CLI / API FastAPI / Web UI)
```

## 5. Tech stack đề xuất (ưu tiên chi phí: miễn phí + online)

Quyết định: dùng **API online** (không chạy LLM local — máy không có GPU),
ưu tiên các dịch vụ có **free tier** để tối ưu chi phí.

- **Ngôn ngữ**: Python 3.11+
- **Framework RAG**: LangChain (hoặc LangGraph nếu cần luồng phức tạp hơn)
- **Vector store**: ChromaDB (local, đơn giản, phù hợp quy mô 160 trang,
  không tốn phí vì chạy hoàn toàn trên máy)
- **Embedding model**: chạy **local, miễn phí 100%** (chỉ chạy 1 lần lúc
  build index, không cần GPU, không lo giới hạn quota API):
  - `bkai-foundation-models/vietnamese-bi-encoder` (khuyên dùng, tối ưu cho
    tiếng Việt) qua thư viện `sentence-transformers`
  - Fallback: `intfloat/multilingual-e5-base`
- **LLM sinh câu trả lời**: gọi **API online, free tier**:
  - **Google Gemini API** (`gemini-2.0-flash` hoặc `gemini-2.5-flash`) —
    lựa chọn ưu tiên, free tier rộng rãi, hiểu tiếng Việt tốt.
    Tích hợp qua `langchain-google-genai`.
  - **Groq API** (Llama 3.1/3.3, Qwen...) — free tier, tốc độ rất nhanh,
    dùng làm phương án dự phòng nếu Gemini bị giới hạn quota.
    Tích hợp qua `langchain-groq`.
  - Lưu ý: free tier có giới hạn request/phút — cần theo dõi khi nhiều
    người dùng cùng lúc, có thể thêm rate-limit/queue phía backend.
- **Document loader**: `PyPDFLoader`/`UnstructuredPDFLoader`/`python-docx`
- **Backend API**: FastAPI
- **Frontend (tuỳ chọn)**: Streamlit (demo nhanh) hoặc React
- **Đánh giá (eval)**: RAGAS hoặc bộ câu hỏi mẫu tự tạo

## 6. Cấu trúc thư mục đề xuất

```
school-regulation-chatbot/
├── data/
│   ├── raw/                 # File quy chế gốc (PDF/DOCX)
│   └── processed/           # Văn bản đã parse, chunk (json/txt)
├── src/
│   ├── ingestion/
│   │   ├── loader.py        # Đọc & parse tài liệu
│   │   ├── chunker.py       # Chia nhỏ theo điều/khoản
│   │   └── build_index.py   # Tạo embedding + lưu vector store
│   ├── rag/
│   │   ├── retriever.py     # Cấu hình retriever, rerank
│   │   ├── prompts.py       # Prompt template (system + few-shot)
│   │   └── chain.py         # RAG chain (LangChain LCEL)
│   ├── api/
│   │   └── main.py          # FastAPI endpoints (/chat, /health)
│   └── eval/
│       └── run_eval.py      # Đánh giá độ chính xác retrieval/answer
├── vectorstore/              # Chroma persist directory (gitignore)
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

## 7. Pipeline xử lý dữ liệu (ingestion)

1. **Load**: đọc PDF/DOCX, cố gắng giữ lại cấu trúc (heading Chương/Điều)
   thay vì parse thành text thuần một khối.
2. **Clean**: loại bỏ header/footer lặp, số trang, ký tự lỗi OCR (nếu có).
3. **Chunking**:
   - Chunk theo đơn vị logic: mỗi **Điều** là 1 chunk (nếu điều dài thì
     chia nhỏ theo khoản), tránh cắt giữa câu.
   - Kích thước chunk ~300-500 tokens, overlap ~50-100 tokens.
   - Lưu metadata cho mỗi chunk: `chuong`, `dieu`, `khoan`, `so_trang`.
4. **Embedding**: encode từng chunk, lưu vào vector store cùng metadata.
5. **Re-index**: script riêng để build lại index khi quy chế cập nhật.

## 8. Retrieval & Generation

- **Retriever**: similarity search (top-k = 4-6) + có thể thêm
  MMR (Maximal Marginal Relevance) để tránh trùng lặp ngữ cảnh.
- **Rerank (tuỳ chọn)**: dùng cross-encoder hoặc Cohere rerank để tăng độ
  chính xác trước khi đưa vào prompt.
- **Prompt template** cần:
  - Chỉ dẫn LLM chỉ trả lời dựa trên ngữ cảnh được cung cấp.
  - Yêu cầu trích dẫn điều/khoản/trang nguồn.
  - Yêu cầu trả lời "Tôi không tìm thấy thông tin này trong quy chế" nếu
    ngữ cảnh không đủ.
- **RAG chain**: dựng bằng LangChain LCEL (`retriever | prompt | llm | parser`).

## 9. Yêu cầu chức năng

- API `/chat`: nhận câu hỏi, trả lời kèm nguồn trích dẫn.
- Giữ lịch sử hội thoại (multi-turn) để hỏi tiếp theo ngữ cảnh trước.
- Hiển thị đoạn văn bản gốc được trích dẫn (để người dùng kiểm chứng).

## 10. Yêu cầu phi chức năng

- Dùng API online (Gemini/Groq free tier) cho phần LLM — cần xử lý retry/
  fallback (VD: Gemini quota hết → chuyển sang Groq) để tránh downtime.
- Embedding chạy local để không phụ thuộc quota khi build/re-index dữ liệu.
- Dễ dàng cập nhật dữ liệu khi quy chế thay đổi (chạy lại `build_index.py`).
- Log lại câu hỏi + câu trả lời để phục vụ đánh giá, cải thiện sau này.
- API key (Gemini/Groq) lưu trong `.env`, không commit vào Git.

## 11. Roadmap triển khai (gợi ý cho Claude Code)

1. Setup project skeleton, requirements.txt, `.env.example`.
2. Viết loader + chunker, test trên 1 phần tài liệu mẫu.
3. Build index (embedding + vector store), kiểm tra retrieval bằng vài
   câu hỏi thử.
4. Viết prompt template + RAG chain, test end-to-end qua CLI.
5. Bọc thành API FastAPI (`/chat`).
6. (Tuỳ chọn) Làm giao diện Streamlit/React đơn giản.
7. Viết bộ câu hỏi mẫu (~20-30 câu) để đánh giá độ chính xác.
8. Viết README hướng dẫn cài đặt & re-index khi có quy chế mới.

## 12. Đánh giá (Evaluation)

- Chuẩn bị bộ câu hỏi mẫu bám sát nội dung thật (VD: "Sinh viên bị cấm thi
  trong trường hợp nào?", "Điều kiện xét học bổng là gì?").
- Đánh giá thủ công: câu trả lời có đúng không, có trích dẫn đúng điều/khoản
  không.
- (Nâng cao) Dùng RAGAS để đo `context precision`, `context recall`,
  `answer relevancy`, `faithfulness`.
