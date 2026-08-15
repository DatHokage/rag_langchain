# 📋 RAG Chatbot Playbook

> Đúc kết từ dự án **Chatbot Quy chế Trường học** (2026-08).
> Mang file này sang dự án chatbot mới để đi nhanh hơn — tránh lặp lại các lỗi đã gặp.

---

## 1. Kiến trúc mẫu (đã chạy thực tế)

```
Tài liệu (PDF/DOCX)
  → loader (giữ cấu trúc Chương/Điều/Khoản)
  → chunker (mỗi Điều = 1 chunk, 300-500 tokens, overlap 50-100)
  → embedding LOCAL (không tốn phí)
  → ChromaDB (persist local)
  → retriever (top-k + MMR)
  → LLM API free tier (chính + fallback) với prompt chống ảo giác
  → Câu trả lời + trích dẫn nguồn
  → CLI / FastAPI /chat / Streamlit
```

**Nguyên tắc quan trọng nhất:** RAG **không cần train** gì cả. Thay dữ liệu = chạy
lại 1 lệnh re-index. LLM và embedding model giữ nguyên.

## 2. Tech stack đã kiểm chứng

| Thành phần | Lựa chọn | Ghi chú |
|---|---|---|
| Framework | LangChain LCEL (`langchain-core 0.3.x`) | Xem mục 14 — có bẫy API |
| Vector store | ChromaDB local | Đủ cho vài trăm trang; batch ≤ 32 docs/lần add |
| Embedding | `bkai-foundation-models/vietnamese-bi-encoder` qua `sentence-transformers` | Chạy local, ~1GB, tiếng Việt tốt; `normalize_embeddings=True` |
| LLM chính | Google Gemini free tier | ⚠️ Xem mục 7 — model bị khai tử thường xuyên |
| LLM fallback | Groq (Llama 3.3 70B) | Free tier rộng hơn, rất nhanh |
| API | FastAPI + uvicorn | lifespan warmup, session LRU, log JSONL |
| UI | Streamlit | Gọi chain in-process, không cần chạy API riêng |
| Loader | `python-docx` (DOCX), `pypdf` (PDF) | DOCX giữ cấu trúc tốt hơn PDF nhiều |

## 3. Ingestion — những gì đáng nhớ

- **Giữ cấu trúc khi parse**: đừng flatten thành 1 khối text. Nhận diện
  heading `Chương/Điều/Khoản/Điểm` bằng regex, lưu vào metadata
  (`chuong`, `dieu`, `khoan`, `so_trang`, `ten_dieu`...). Metadata này chính là
  thứ tạo nên trích dẫn "Điều X, trang Y" trong câu trả lời.
- **Chunk theo đơn vị logic** (mỗi Điều), chỉ cắt nhỏ theo Khoản khi điều quá dài.
  Không cắt giữa câu.
- **Re-index sạch**: `shutil.rmtree(vectorstore)` trước khi build lại — tránh
  lẫn dữ liệu cũ/mới.
- **Batch size 32** khi add vào Chroma (giới hạn 41.666 ops/request).
- **DOCX > PDF**: parser PDF mất cấu trúc heading. Nếu có thể, xin tài liệu
  bản Word hoặc chuyển PDF → DOCX trước.
- 💡 Bài học: header lặp lại giống hệt nhau ở mọi chunk (VD: tên quyết định dài)
  làm embedding các chunk giống nhau hơn mức cần → nhiễu retrieval. Cân nhắc
  rút gọn header trong `page_content`, giữ bản đầy đủ ở metadata.

## 4. Retriever

```python
# similarity top-k + MMR chống trùng lặp
vs.as_retriever(search_type="mmr",
                search_kwargs={"k": 5, "fetch_k": 20})   # lambda_mult=0.5 mặc định
```

- `k=4-6` đủ cho đa số trường hợp; `fetch_k` ≥ 3×k để MMR có lựa chọn.
- **Tìm thấy (đừng mất thời gian như dự án này):**
  - Tăng `k` hay chỉnh `lambda_mult` chỉ **đánh đổi** câu miss này lấy câu miss
    khác khi nguyên nhân là **khoảng cách ngữ nghĩa thật sự** (VD: tài liệu viết
    tắt "HB KKHT", câu hỏi viết đầy đủ "học bổng khuyến khích học tập").
  - Đúng thuốc cho bệnh đó là **query expansion / bảng từ viết tắt** (chèn dạng
    chuẩn vào câu hỏi trước khi retrieve), không phải vặn retriever.
- Hit-rate tham khảo: **96% (26/27)** với top-5 MMR trên tài liệu pháp quy tiếng Việt.

## 5. Prompt chống ảo giác (5 quy tắc đã kiểm chứng)

```text
Bạn là trợ lý tra cứu <LĨNH VỰC>. Bạn CHỈ trả lời dựa trên NGỮ CẢNH được
cung cấp, không dùng kiến thức ngoài, tuyệt đối không bịa thông tin.

QUY TẮC:
1. Trả lời bằng tiếng Việt, chính xác, súc tích, đi thẳng vào câu hỏi.
2. Luôn trích dẫn nguồn cho MỖI luận điểm: (Điều X, <tên quy chế>, trang ~Z).
3. Nếu ngữ cảnh KHÔNG chứa thông tin, trả lời chính xác:
   "Toi khong tim thay thong tin nay trong quy che." — kèm gợi ý từ khóa.
4. Nếu có bảng biểu, tóm tắt thành ý chính / gạch đầu dòng.
5. Nếu câu hỏi liên quan một quy chế cụ thể, ưu tiên đúng quy chế đó.

NGỮ CẢNH (mỗi đoạn bắt đầu bằng header "Phần > Chương > Điều"):
{context}
```

- Câu từ chối **cố định nguyên văn** → eval tự động check được bằng regex
  (`khong tim thay thong tin` — viết không dấu để LLM dễ tuân thủ chính xác).
- Context ghép dạng `[Đoạn 1]\n...` + header cấu trúc — LLM trích dẫn nguồn
  chính xác hơn hẳn khi mỗi đoạn có header rõ.
- Multi-turn: `MessagesPlaceholder("chat_history", optional=True)`, giữ
  **6 message gần nhất** (3 cặp hỏi-đáp) là đủ.

## 6. Pattern Fallback LLM (code mẫu dùng lại được)

```python
class FallbackLLM(Runnable):
    def __init__(self, primary, fallback):  # import lazy trong factory
        self.primary, self.fallback = primary, fallback
        self.last_provider = ""

    def invoke(self, input, config=None, **kwargs):
        if self.primary is not None:
            try:
                result = self.primary.invoke(input, config=config, **kwargs)
                self.last_provider = "gemini"
                return result
            except Exception as e:
                if self.fallback is None:
                    raise
                logger.warning("Gemini loi -> chuyen Groq: %s", str(e)[:200])
        self.last_provider = "groq"
        return self.fallback.invoke(input, config=config, **kwargs)
```

- Import provider SDK **lazy** (trong hàm factory) để không crash khi chưa cài
  package của 1 provider.
- Luôn trả `provider` kèm kết quả — để log, để hiển thị, để debug quota.

## 7. ⚠️ Gemini free tier — thực tế năm 2026 (quan trọng nhất)

1. **Model bị khai tử thường xuyên, đặc biệt với key mới:**
   - `gemini-2.0-flash` → 404 "no longer available"
   - `gemini-2.5-flash` → 404 "no longer available to new users"
   - Đừng hardcode tin vào docs — **probe trực tiếp bằng key thật** trước:

   ```python
   # liệt kê model + test gọi thật
   GET https://generativelanguage.googleapis.com/v1beta/models?key=<KEY>
   POST .../v1beta/models/<MODEL>:generateContent?key=<KEY>
   ```
2. **Key mới free tier chỉ ~20 request/NGÀY cho mỗi model**
   (quota `GenerateRequestsPerDayPerProjectPerModel-FreeTier: 20`).
   Rất chặt — đủ demo nhưng không đủ chạy eval 30 câu 1 lần.
   Giải pháp: tạo thêm key (mỗi key 1 hạn mức), hoặc thêm Groq fallback,
   hoặc chia eval nhiều ngày (`--llm -k 5`).
3. Lỗi 429 của Gemini trả kèm `retry_delay` — `langchain-google-genai` tự retry
   bằng tenacity; nếu quota ngày hết thì retry vô ích, phải xử lý thân thiện
   (UI báo "hết quota hôm nay, mai thử lại").
4. Groq free tier giới hạn theo phút (không theo ngày) → hợp làm fallback hơn.

## 8. FastAPI — pattern đã chạy tốt

- `lifespan` warmup chain 1 lần lúc khởi động → câu hỏi đầu không phải chờ tải model.
- Session in-memory `OrderedDict` + LRU 200 session, lịch sử 6 message/session.
- Log mỗi cặp hỏi-đáp ra `logs/chat_log.jsonl` (ts, session, question, answer,
  provider, sources) — nguồn dữ liệu để cải thiện sau này.
- Check vectorstore tồn tại → trả **503 kèm câu lệnh fix** thay vì lỗi chung chung.
- Pydantic model cho request/response (`min_length`, `max_length`) — chặn rác đầu vào.

## 9. Streamlit — pattern đã chạy tốt

- Gọi chain **in-process** (`from src.rag.chain import ask`) — không cần chạy
  FastAPI riêng cho demo.
- `@st.cache_resource` cho warmup model/vectorstore (tải 1 lần/phiên).
- Tách 2 list trong `session_state`:
  - `messages`: để render UI (role, content, sources, provider)
  - `history`: list `BaseMessage` gửi vào chain
- Nút gợi ý câu hỏi khi chat trống; `st.expander` cho khung nguồn trích dẫn
  (nhãn Điều/Khoản/Trang + văn bản gốc thu gọn).
- Bắt lỗi quota 429 → thông báo tiếng Việt thân thiện thay vì stack trace.
- Chạy headless test không cần trình duyệt:
  `streamlit.testing.v1.AppTest` + `streamlit run --server.headless true`.

## 10. Đánh giá 2 lớp (chạy offline được 1 lớp)

**Lớp 1 — Retrieval (không tốn quota):**
- Bộ câu hỏi mẫu ~30 câu, mỗi câu kèm `expected_dieu` / `expected_muc`.
- Hit-rate = % câu mà top-k chunk chứa đúng điều/quy chế kỳ vọng.
- Thêm **2-3 câu ngoài phạm vi** ("Pizza ngon nhất ở đâu?") để kiểm tra từ chối.

**Lớp 2 — Câu trả lời (tốn quota):**
- Chạy qua chain, in câu trả lời + nguồn để đánh giá thủ công.
- Câu `expected_answer: "REFUSE"` → check regex câu từ chối tự động.
- Chạy `-k N` để chia nhỏ theo quota ngày.

**Chuẩn bị bộ câu hỏi:** bám sát tài liệu thật, phủ đều các chương/mục,
đánh dấu sẵn điều kỳ vọng — mất 1 buổi nhưng dùng được mãi.

## 11. Vận hành & cập nhật dữ liệu

```powershell
# Cập nhật dữ liệu MỚI = chỉ 2 bước, KHÔNG train lại:
#   1. Đặt file mới vào data/raw/
#   2. python -m src.ingestion.build_index
```

- `.env` giữ keys (gitignore bắt buộc) + tên model + đường dẫn + top-k.
  Kèm `.env.example` có chú thích chỗ lấy key.
- Windows console: `sys.stdout.reconfigure(encoding="utf-8")` đầu mỗi entrypoint
  (cp1252 không in được tiếng Việt).
- Lần đầu chạy tải embedding model ~1GB vào cache — các lần sau chạy ngay.

## 12. 🔄 Quy trình thay đổi dữ liệu đầu vào / thay quy chế mới

**Nguyên tắc:** thay dữ liệu chỉ là thay `data/raw/` + chạy lại **1 lệnh
re-index** — KHÔNG train lại, KHÔNG sửa code LLM/embedding. Nhưng có những
thứ phải cập nhật **đồng bộ** cùng dữ liệu, tùy 1 trong 3 trường hợp sau:

### Trường hợp A — Cùng bộ quy chế, có phiên bản mới (thường gặp nhất)
VD: Sổ tay sinh viên 2024-2025 → 2025-2026, số điều và cấu trúc gần như giữ nguyên.

1. **Sao lưu index cũ trước khi xóa** (build_index tự `shutil.rmtree`!):
   `Copy-Item vectorstore vectorstore_backup_20260815` — để so sánh/rollback
   nếu index mới tệ hơn.
2. Xóa/đổi file cũ trong `data/raw/` (đừng để **cả 2 phiên bản cùng lúc** —
   chatbot sẽ trộn lẫn điều khoản cũ và mới). File tạm `~$...` của Word
   đang mở được tự bỏ qua, nhưng nên đóng Word cho sạch.
3. `python -m src.ingestion.build_index` → xem số chunk in ra có hợp lý so
   với lần trước không (đột biến = cấu trúc parse khác, kiểm tra ngay).
4. **Rà bộ câu hỏi eval** (`tests/sample_questions.json`): số hiệu Điều rất
   dễ bị **đánh số lại** giữa các năm → cập nhật `expected_dieu` cho từng câu.
5. Chạy `python -m src.eval.run_eval` (chỉ lớp retrieval, không tốn quota).
   Nếu hit-rate tụt so với mốc cũ thì xử lý **trước** khi chạy lớp LLM.
6. Nếu đổi **tên** quy chế: cập nhật prompt (`src/rag/prompts.py` — chỗ
   "trợ lý tra cứu <LĨNH VỰC>"), gợi ý câu hỏi trong `app.py`
   (`CAU_HOI_GOI_Y`), README.

### Trường hợp B — Quy chế khác hẳn về cấu trúc (lưu ý nhiều nhất)
VD: chuyển từ "quy chế đào tạo theo Điều/Khoản" sang tài liệu dạng
mục lục tự do, FAQ, biểu mẫu...

- **Loader/chunker là chỗ phải sửa đầu tiên**: regex nhận diện
  `Chương/Điều/Khoản` (`src/ingestion/loader.py`, `chunker.py`) được viết cho
  văn bản pháp quy. Cấu trúc mới mà cố dùng regex cũ → chunk vỡ vụn hoặc dồn
  cục, metadata sai → trích dẫn nguồn sai theo.
- Metadata chunk (`dieu`, `khoan`, `so_trang`...) gắn chặt với: câu trích dẫn
  trong prompt → context header → UI nguồn. Đổi tên/khóa metadata phải sửa
  đồng bộ cả 4 chỗ, nếu không sẽ im lặng mất trích dẫn.
- Prompt chống ảo giác (mục 5) viết theo cấu trúc cũ ("mỗi đoạn bắt đầu bằng
  Phần > Chương > Điều") → sửa lại mô tả header cho khớp cấu trúc mới.
- Viết lại bộ câu hỏi eval **từ đầu** cho tài liệu mới; giữ lại vài câu
  REFUSE ("Pizza ngon nhất ở đâu?") để test từ chối.
- Câu hỏi cũ còn lưu trong `logs/chat_log.jsonl` thuộc về tài liệu cũ —
  đừng lấy nó làm bộ eval cho quy chế mới.

### Trường hợp C — Thêm tài liệu vào bộ hiện có
1. Cứ để cả file cũ và mới trong `data/raw/` — re-index là build lại **toàn
   bộ**, không cần index tăng dần.
2. Nếu tài liệu mới là **bản sửa lỗi** của tài liệu cũ → xóa bản cũ đi,
   nếu không chatbot sẽ trả lời lẫn lộn 2 phiên bản (và hay trích dẫn bản cũ
   hơn vì chunk cũ thường nhiều hơn).
3. Câu từ chối cố định "khong tim thay thong tin **trong quy che**" — nếu bộ
   tài liệu giờ không còn là quy chế, sửa lại câu này cho đúng phạm vi mới.

### Checklist nhanh trước khi giao bản cập nhật

- [ ] Chỉ 1 phiên bản của mỗi tài liệu trong `data/raw/`
- [ ] Đã backup vectorstore cũ trước khi re-index
- [ ] Số chunk sau build không đột biến so với lần trước
- [ ] `expected_dieu` trong bộ eval đã rà lại theo tài liệu mới
- [ ] Retrieval hit-rate ≥ 90% rồi mới chạy eval lớp LLM
- [ ] Tên quy chế trong prompt / gợi ý / README đã đồng bộ

## 13. ✅ Checklist khởi động dự án chatbot mới

- [ ] Copy cấu trúc thư mục: `src/{ingestion,rag,api,eval}` + `data/{raw,processed}`
- [ ] `.env.example` + `.gitignore` (`.env`, `vectorstore/`, `logs/`, `.venv/`)
- [ ] Build index offline trước (không cần key) → test retrieval bằng vài câu tay
- [ ] **Probe model Gemini bằng key thật** trước khi hardcode tên model
- [ ] Prompt chống ảo giác + câu từ chối cố định
- [ ] Fallback LLM (Gemini → Groq)
- [ ] Bộ câu hỏi mẫu 25-30 câu kèm expected_dieu + vài câu REFUSE
- [ ] Eval retrieval (offline) đạt ≥ 90% rồi mới động đến LLM
- [ ] UI (Streamlit) + thông báo lỗi quota thân thiện
- [ ] README: cài đặt, lấy key, re-index

## 14. 🪤 Bẫy đã gặp thực tế (đừng lặp lại)

1. **LCEL: `itemgetter("x") | fn` → `TypeError`** trên langchain-core 0.3.86.
   Fix: bọc `RunnableLambda(itemgetter("x")) | fn`.
2. **Tên biến tiếng Việt có dấu cách** (`GỢI Ý = [...]`) → SyntaxError.
   Tiếng Việt có dấu OK cho *tên biến đơn* (`GỢI_Ý`) nhưng tránh — dùng ASCII
   (`CAU_HOI_GOI_Y`) cho an toàn.
3. **Cứ tưởng config retriever là thuốc chữa miss** — mất thời gian thử
   top-k 5→8, fetch_k 20→80, lambda 0.5→1.0; kết quả net không đổi.
   Miss do ngữ nghĩa (viết tắt) thì chữa ở dữ liệu/query, không phải retriever.
4. **Tin tên model trong docs cũ** — Gemini khai tử model liên tục; luôn probe.
5. **Chạy eval nguyên bộ khi quota chỉ 20/ngày** — sẽ chết giữa chừng ở câu 13.
   Luôn kiểm tra quota còn bao nhiêu trước khi batch-run.
6. **HF Hub rate limit**: warning "unauthenticated requests" khi tải embedding —
   đặt `HF_TOKEN` nếu tải thường xuyên.
7. **Chạy script từ ngoài thư mục gốc** → `ModuleNotFoundError: No module named
   'src'` — nhớ `sys.path.insert(0, PROJECT_ROOT)` hoặc chạy từ root dự án.
8. **`tenacity` retry im lặng** — khi hết quota ngày, SDK tự retry 5-6 lần
   (2s→4s→8s→16s→32s) trông như treo; log cảnh báo sớm ở tầng của mình.

---

*File này là tài liệu sống — sau mỗi dự án chatbot mới, quay lại bổ sung
bài học mới vào mục 14.*
