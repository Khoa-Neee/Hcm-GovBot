# STATUS.md

Tài liệu này ghi lại trạng thái hiện tại của dự án HCM GovBot.

## 1. Tổng Quan Trạng Thái

Dự án đã có một bản local chạy thật với dữ liệu thật từ Cổng Dịch vụ công Quốc gia, Supabase PostgreSQL, pgvector, FastAPI và React.

Đã hoàn thành các phần nền tảng:

- Schema Supabase.
- Crawler thủ tục hành chính Thành phố Hồ Chí Minh.
- Upsert database.
- Soft delete bằng `is_active`.
- Hash nội dung để phát hiện thay đổi.
- Supabase pgvector embedding search.
- Backend API FastAPI.
- Frontend React/Tailwind.
- Dashboard thống kê.
- Chatbot RAG theo thủ tục hành chính.
- Google login qua Supabase Auth để lưu lịch sử chat.
- Context editor cho chatbot.
- Scheduler 24h tùy chọn.

## 2. Dữ Liệu

Dữ liệu đã crawl vào Supabase:

- `2154` thủ tục active.
- `2151` thủ tục hành chính thường.
- `3` thủ tục hành chính liên thông.

Vector đã sync:

- `2154` embedding trong `procedure_embeddings`.
- Model embedding: `gemini-embedding-001`.
- Dimension: `768`.
- Search bằng cosine similarity qua pgvector.

Nguồn hiện đang dùng:

```text
https://thutuc.dichvucong.gov.vn/p/home/dvc-tthc-thu-tuc-hanh-chinh.html
https://thutuc.dichvucong.gov.vn/p/home/dvc-tthc-thu-tuc-hanh-chinh-lien-thong.html
```

Phần dịch vụ công trực tuyến đã được bỏ qua theo yêu cầu.

## 3. Backend

Backend FastAPI hiện có:

```text
GET  /api/health
GET  /api/auth/supabase-config
GET  /api/crawler/preview
GET  /api/procedures
GET  /api/procedures/{procedure_id}
GET  /api/filters
GET  /api/stats/overview
POST /api/search/vector
POST /api/chat/sessions
GET  /api/chat/sessions
GET  /api/chat/sessions/{session_id}
POST /api/chat/sessions/{session_id}/messages
PATCH /api/chat/sessions/{session_id}/context
POST /api/chat/context/summarize
POST /api/chat/local/messages
```

CLI hiện có:

```text
crawl-preview
detail-preview
sync
sync-source-ids
vector-sync
vector-search
vector-count
db-count
llm-test
```

Scheduler:

- Có `AppScheduler`.
- Bật bằng `SCHEDULER_ENABLED=true` trong `.env`.
- Khi backend start, scheduler có thể chạy ngay sau vài giây bằng `SCHEDULER_RUN_ON_STARTUP=true`.
- Sau đó chạy sync crawler và vector sync theo `SCHEDULER_INTERVAL_HOURS`, mặc định 24h.
- Có khóa nội bộ để tránh chạy song song nếu lần crawl trước chưa xong.

## 4. Frontend

Frontend hiện có 3 tab chính:

- Tra cứu.
- Thống kê.
- Hỏi AI.

Trang tra cứu:

- Search theo tên/mã thủ tục.
- Filter theo loại thủ tục.
- Filter theo lĩnh vực.
- Filter theo cơ quan.
- Xem chi tiết thủ tục.

Trang chi tiết:

- Mã thủ tục.
- Tên thủ tục.
- Cơ quan thực hiện.
- Đối tượng.
- Thời hạn.
- Phí/lệ phí.
- Hồ sơ.
- Trình tự.
- Điều kiện.
- Căn cứ pháp lý.
- Link nguồn.

Thống kê:

- Tổng thủ tục.
- Số thủ tục thường/liên thông.
- Thống kê theo lĩnh vực.
- Thống kê theo cơ quan.
- Thủ tục mới cập nhật gần đây.

Chatbot:

- Đăng nhập Google nếu muốn lưu lịch sử.
- Không đăng nhập vẫn chat được nhưng không lưu DB.
- Lịch sử chat bên trái.
- Khung chat scroll riêng, không kéo dài cả trang.
- Timer đếm giây khi chờ AI.
- Panel thủ tục dùng để trả lời bên phải.
- Xóa thủ tục khỏi context.
- Tìm và thêm thủ tục vào context.
- Context giới hạn tối đa 3 thủ tục.
- Hiển thị thời gian suy luận cho câu trả lời AI.
- Chat đã đăng nhập tự xóa sau 7 ngày không hỏi thêm.

## 5. Chatbot Flow

Câu hỏi đầu tiên:

```text
user_type + question
  -> LLM đoán tối đa 3 tên thủ tục
  -> pgvector lấy 2 thủ tục gần nhất cho mỗi tên
  -> deduplicate
  -> sort theo similarity
  -> giữ tối đa 3 thủ tục
  -> Gemini tóm tắt song song
  -> trả lời trực tiếp theo câu hỏi, không liệt kê toàn bộ thủ tục gần đúng
  -> lưu chat session nếu đã đăng nhập
```

Câu hỏi tiếp theo:

```text
message mới
  -> dùng procedure_context hiện tại
  -> không search lại nếu chưa cần
  -> nếu vượt context, AI nói rõ và hỏi có muốn tìm thủ tục khác không
```

Pool Gemini API keys:

- Đọc `GEMINI_API_KEY_1` đến `GEMINI_API_KEY_10`.
- Key rỗng không dùng.
- Với nhiều Gemini API key, tóm tắt context chạy song song tối đa 3 request.
- Nếu một key lỗi, client thử fallback qua các key còn lại.

## 6. Auth Và Lưu Lịch Sử Chat

Đã chuyển sang Google login qua Supabase Auth.

Frontend:

- Nút `Tiếp tục với Google`.
- Redirect qua Supabase Auth.
- Sau redirect, frontend lấy access token từ URL hash.
- Token được lưu trong `localStorage`.

Backend:

- Đọc JWT từ `Authorization: Bearer ...`.
- Verify user qua Supabase Auth endpoint.
- Nếu có user, session được lưu với `chat_sessions.user_id`.
- Nếu không có user, chat chạy local và không lưu DB.

Database:

- Migration `0003_chat_auth.sql` thêm `chat_sessions.user_id`.
- Có RLS policy cho user đọc session/message của chính mình.

Lưu ý:

- Chat session tự xóa sau 7 ngày nếu không có tin nhắn mới.
- Mỗi câu hỏi mới cập nhật lại thời hạn lưu thêm 7 ngày.
- Chưa có chức năng xóa lịch sử chat thủ công từ UI.

## 7. Supabase Migrations

Các migration hiện có:

```text
supabase/migrations/0001_initial_schema.sql
supabase/migrations/0002_pgvector_embeddings.sql
supabase/migrations/0003_chat_auth.sql
```

Ý nghĩa:

- `0001`: schema thủ tục, crawler logs, chat tables ban đầu.
- `0002`: pgvector, bảng `procedure_embeddings`, RPC `match_procedure_embeddings`.
- `0003`: liên kết chat với `auth.users`, index và RLS policy cho chat.

## 8. Cấu Hình Env

Backend cần:

```text
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
GEMINI_API_KEY_1..10
GEMINI_CHAT_MODEL
GEMINI_EMBEDDING_MODEL
EMBEDDING_DIMENSIONS
```

Frontend:

- Có thể dùng `VITE_API_BASE_URL`.
- Không bắt buộc duplicate `VITE_SUPABASE_URL` và `VITE_SUPABASE_ANON_KEY` nữa.
- Frontend lấy Supabase public config qua `/api/auth/supabase-config`.

Google OAuth:

- Google Client ID/Secret cấu hình trong Supabase Dashboard.
- Google Client Secret không đưa vào frontend.

## 9. Đã Kiểm Tra

Những kiểm tra đã chạy nhiều lần trong quá trình phát triển:

- Backend import OK.
- Frontend build OK.
- CLI db/vector đã chạy được trước đó.
- Vector search CLI đã trả kết quả đúng.
- Thống kê đã sửa lỗi Supabase giới hạn 1000 rows bằng pagination.

Lưu ý vận hành:

- Nếu frontend gọi endpoint mới bị `404`, thường là backend cũ chưa restart.
- Nếu Vite không nhận env, cần restart Vite dev server.
- Nếu Google login lỗi, kiểm tra redirect URI trong Google Cloud và Supabase Auth Provider.

## 10. Việc Còn Lại

Ưu tiên gần:

- Thêm chức năng xóa lịch sử chat.
- Thêm nút `Hỏi AI về thủ tục này` ở trang chi tiết.
- Thêm test API cho chat và procedures.
- Thêm rate limiter/cooldown cho Gemini key bị `429`.

Ưu tiên deploy:

- Cấu hình Render backend.
- Cấu hình Vercel frontend.
- Cấu hình CORS production.
- Bật scheduler hoặc dùng Render Cron/GitHub Actions.
- Kiểm tra secret trên môi trường deploy.

Ưu tiên dữ liệu:

- Chuẩn hóa `target_audience` vì dữ liệu nguồn không nhất quán.
- Chuẩn hóa `implementation_agency` bị lặp tên.
- Tách attachments từ JSON sang `procedure_attachments` nếu cần.

## 11. Lệnh Chạy Local

Backend:

```powershell
conda activate hcm-govbot
cd apps/api
python -m app.main
```

Frontend:

```powershell
cd apps/web
npx vite --host 127.0.0.1
```

Kiểm tra API:

```text
http://127.0.0.1:8000/docs
```

Mở frontend:

```text
http://127.0.0.1:5173
```
