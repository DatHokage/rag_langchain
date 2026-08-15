# 🚀 Deploy Guide — Phương án 1: Hugging Face Spaces (khuyên dùng)

> Đưa chatbot Quy chế (`app.py` — Streamlit) lên internet **miễn phí**, không cần server.
> Áp dụng cho dự án này: embedding local + ChromaDB + Streamlit.

---

## 1. Vì sao chọn Hugging Face Spaces

| Thông số gói CPU miễn phí | Giá trị | Ý nghĩa với dự án |
|---|---|---|
| CPU | 2 cores | Embedding + retrieval chạy thoải mái (đã chạy local trên máy cấu hình tương đương) |
| RAM | **16 GB** | Điểm ăn tiền: embedding model `vietnamese-bi-encoder` (~1 GB) + ChromaDB index cho 160 trang + Streamlit cùng chạy trong RAM |
| Đĩa | 50 GB, **không lưu trữ lâu dài** | Đủ chỗ; nhưng file sinh ra lúc chạy (log...) sẽ mất khi Space restart — không sao vì vectorstore được đóng gói sẵn trong repo |
| SDK | Hỗ trợ **Streamlit ngay từ đầu** | Không phải viết Dockerfile, không phải chạy FastAPI riêng |
| Deploy | Kết nối repo Git — **mỗi lần commit/push tự rebuild** | Cập nhật quy chế = re-index ở máy mình rồi push, không thao tác thủ công trên web |
| Ngủ | Space tự ngủ sau **~48 giờ không ai truy cập**, tự khởi động lại khi có người vào | Demo/đồ án không cần online 24/7 — chấp nhận được |

**So sánh nhanh:** Streamlit Community Cloud chỉ có ~690 MB–2.7 GB RAM —
rủi ro thiếu khi Streamlit + embedding model + vector store cùng chạy.
HF Spaces cho 16 GB nên đây là phương án khuyên dùng.

---

## 2. Chuẩn bị — những gì Space sẽ nhận

Space chính là **repo Git chứa toàn bộ dự án này**, thêm 2 thứ:

| File | Trạng thái | Ghi chú |
|---|---|---|
| `app.py`, `src/` | ✅ Đã có | Entry point là `app.py` |
| `requirements.txt` | ✅ Đã có | Space tự `pip install` lúc build |
| `vectorstore/` (~11 MB) | ✅ Đã có | **Phải commit vào repo** — index ChromaDB đóng gói sẵn, Space không build lại index |
| `data/raw/` | ✅ Đã có | Commit để Space có đủ dữ liệu gốc (làm bằng chứng). Space ở chế độ **Private** nên không lộ ra ngoài |
| `.env` | ⛔ **KHÔNG commit** | API keys đưa vào Secrets của Space (mục 5) |
| `README.md` | ✏️ Cần thêm frontmatter | HF Spaces đọc YAML ở đầu `README.md` để biết cách chạy (mục 4) |
| `.gitignore` | ✅ Đã chỉnh | Chỉ còn chặn rác (`__pycache__`, `.env`, `logs/`...) — vectorstore và dữ liệu **được** commit (mục 3) |

> 🔒 **Quyết định bảo mật:** `.gitignore` gốc của dự án chặn toàn bộ dữ liệu
> và vectorstore vì quy chế là tài liệu **nội bộ, không public**. Vì vậy Space
> **bắt buộc ở chế độ Private** — dữ liệu commit vào repo của Space vẫn không ai
> xem được. KHÔNG push repo này lên GitHub hay bất kỳ nơi công khai nào.

Lưu ý: embedding model (~1 GB) **không** đóng gói vào repo — Space tự tải từ
HF Hub lúc khởi động (lần đầu mất 1–3 phút, đã có spinner
"Đang tải mô hình..." trong `app.py`).

---

## 3. Bước 1 — `.gitignore` (đã chỉnh sẵn cho Private Space)

`.gitignore` hiện tại đã được chỉnh: **không còn** chặn `vectorstore/`,
`data/raw/`, `*.docx` — để Space nhận đủ index + tài liệu gốc. Chỉ còn chặn:

```gitignore
.env                  # secrets — đưa vào Secrets của Space
__pycache__/  .venv/  logs/  *.log   # rác runtime
~$*                                  # file lock tạm của Word
.streamlit/secrets.toml              # secrets của Streamlit
```

Kiểm tra nhanh trước khi push:

```powershell
git status   # phai thay vectorstore/ va data/raw/...docx trong danh sach
```

> ⚠️ Nếu `vectorstore/` không hiện trong `git status` → đang còn dòng ignore
> cũ chặn; kiểm tra lại `.gitignore`. Và nhớ: repo này chỉ sống trên HF Space
> private, không push sang GitHub.

---

## 4. Bước 2 — Thêm YAML frontmatter vào `README.md`

HF Spaces cấu hình Space qua khối YAML ở **đầu file** `README.md`. Dán khối này
lên trên cùng file `README.md` hiện tại (nội dung cũ giữ nguyên bên dưới):

```markdown
---
title: Chatbot Quy che
emoji: 🏫
colorFrom: blue
colorTo: indigo
sdk: streamlit
sdk_version: "1.51.1"   # ghi đúng version đang chạy: pip show streamlit
app_file: app.py
pinned: false
---
```

- `app_file: app.py` → Space tự chạy `streamlit run app.py`.
- `sdk_version`: kiểm tra bằng `pip show streamlit` rồi điền số thực tế —
  lệch version đôi khi gây lỗi build.

---

## 5. Bước 3 — Khai báo API keys (Secrets)

`.env` không được commit, nên khai báo keys trực tiếp trên Space:

1. Mở Space trên web → **Settings** → **Variables and secrets**
2. Bấm **New secret**, thêm từng biến (tên phải **trùng** với trong `.env`):

| Tên biến | Giá trị | Bắt buộc? |
|---|---|---|
| `OPENROUTER_API_KEY` | key OpenRouter | Có (LLM chính) |
| `GOOGLE_API_KEY` | key Gemini | Nên có (fallback) |
| `GEMINI_MODEL` | tên model Gemini đã probe | Tùy chọn |
| `OPENROUTER_MODELS` | danh sách model `:free` | Tùy chọn |
| `HF_TOKEN` | token HF Hub | Tùy chọn — chống rate limit khi tải embedding (bẫy số 6 trong playbook) |

Không cần khai `VECTORSTORE_DIR` / `RETRIEVER_TOP_K` — code đã có default
(`vectorstore/`, top-k=5).

Secret chỉ hiện dưới dạng biến môi trường trong container — không lộ trong
repo, đúng nguyên tắc của `.env`.

---

## 6. Bước 4 — Tạo Space và push code

### 6.1 Tạo Space

1. Vào https://huggingface.co/new-space
2. **Space name**: `chatbot-quy-che` (tùy thích)
3. **SDK**: chọn **Streamlit**; Hardware: **CPU basic (Free)**
4. Visibility: **Private** (bắt buộc — repo chứa tài liệu quy chế nội bộ;
   gói free vẫn hỗ trợ Space private)
5. Bấm **Create Space**

### 6.2 Push code lên

Dự án này **chưa có repo Git** — khởi tạo tại thư mục gốc:

```powershell
cd E:\rag_langchain
git init
git add .
git commit -m "San sang deploy len HF Spaces"

git remote add origin https://huggingface.co/spaces/<USER>/chatbot-quy-che
git branch -M main
git push -u origin main
```

- Đăng nhập HF bằng token: chạy `huggingface-cli login` (cài bằng
  `pip install huggingface_hub`) hoặc dùng Git Credential Manager khi push
  hỏi mật khẩu — token tạo tại https://huggingface.co/settings/tokens (loại Write).
- Push xong, Space tự build. Theo dõi tab **Logs** trên trang Space:
  build lần đầu ~5–10 phút (cài torch + tải embedding model).

> Cách thay thế không dùng Git: tab **Files** → **Add file** → upload từng file.
> Chỉ hợp lý khi sửa nhanh 1 file; về lâu dài vẫn nên dùng Git để có lịch sử.

### 6.3 Kiểm tra

- Trạng thái Space chuyển **Running** → bấm tab **App** để mở chatbot.
- Câu hỏi đầu tiên sẽ chậm 1–3 phút (tải embedding model vào RAM) — sau đó nhanh.
- Thử 1 câu trong `CAU_HOI_GOI_Y`, kiểm tra trích dẫn Điều/Khoản/Trang hiện đúng.
- Kiểm tra badge model trả lời + sidebar trạng thái hệ thống (vector store ✓, API key ✓).

---

## 7. Quy trình cập nhật sau này (quy chế mới / sửa code)

Mọi thay đổi đều theo một vòng duy nhất — **không thao tác gì trên web Space**:

```powershell
# 1. Cập nhật dữ liệu/quy chế theo playbook mục 12 (re-index locally)
python -m src.ingestion.build_index

# 2. Test nhanh retrieval
python -m src.eval.run_eval

# 3. Commit + push -> Space tự rebuild
git add .
git commit -m "Cap nhat quy che 2025-2026"
git push
```

Sửa code (`app.py`, `src/`) cũng tương tự: commit + push là tự deploy lại.
Đổi API key thì chỉ cần sửa Secret trong Settings — không cần push.

---

## 8. Giới hạn của gói miễn phí — biết trước để khỏi ngỡ ngàng

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Space "ngủ", người đầu tiên vào phải chờ vài phút | Tự ngủ sau ~48 giờ không ai truy cập | Bình thường — tự khởi động lại. Demo đồ án: mở tab trước buổi bảo vệ ~10 phút cho Space tỉnh |
| File log mới sinh biến mất sau restart | Đĩa 50 GB không lưu trữ lâu dài | Thiết kế hiện tại đã OK: vectorstore đóng gói trong repo; `logs/chat_log.jsonl` chỉ có ý nghĩa khi chạy local |
| Câu đầu tiên sau khi tỉnh chậm | Embedding model phải tải lại vào RAM | Đã có spinner trong `app.py`; ghi chú cho người dùng |
| Build thỉnh thoảng thất bại khi tải model | HF Hub rate limit (IP dùng chung) | Thêm `HF_TOKEN` vào Secrets (mục 5) |
| Muốn online 24/7, nhiều người dùng đồng thời | Gói free: 1 phiên, sleep tự động | Ngoài phạm vi đồ án; nếu cần thì nâng cấp CPU paid hoặc tự host |

---

## 9. Checklist trước khi bấm push

- [ ] Space tạo ở chế độ **Private** (repo chứa dữ liệu quy chế)
- [ ] `git status` hiện đủ `vectorstore/` và `data/raw/*.docx`
- [ ] `README.md` có YAML frontmatter (`sdk: streamlit`, `app_file: app.py`)
- [ ] `.gitignore` vẫn chặn `.env` và `logs/`
- [ ] `vectorstore/` đã build mới nhất (`python -m src.ingestion.build_index`)
- [ ] Secrets đã khai đủ trên Space (`OPENROUTER_API_KEY`, `GOOGLE_API_KEY`)
- [ ] Chạy thử `streamlit run app.py` ở máy còn tốt trước khi push
- [ ] (Tùy chọn) `HF_TOKEN` để tránh rate limit lúc build
