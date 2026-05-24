# SCHEMA.md

Tài liệu này mô tả schema Supabase PostgreSQL hiện tại của HCM GovBot và cách dữ liệu đi qua crawler, database, pgvector, dashboard thống kê và chatbot.

## 1. Tổng Quan

Nguồn dữ liệu chính đến từ Cổng Dịch vụ công Quốc gia, lọc theo `UBND Thành phố Hồ Chí Minh`:

- Thủ tục hành chính: `administrative`
- Thủ tục hành chính liên thông: `interlinked`

Luồng dữ liệu chính:

```text
Cổng DVC Quốc Gia
  -> crawler FastAPI CLI
  -> procedures
  -> Gemini embedding
  -> procedure_embeddings bằng pgvector
  -> API tra cứu / thống kê / chatbot
```

Hiện tại hệ thống dùng:

- `procedures` làm bảng dữ liệu gốc.
- `procedure_embeddings` làm bảng vector search.
- `chat_sessions` và `chat_messages` để lưu lịch sử chat khi user đăng nhập Google qua Supabase Auth.
- Nếu user không đăng nhập, chat vẫn dùng được nhưng không lưu lịch sử vào database.

## 2. `procedures`

Bảng trung tâm của hệ thống. Mỗi dòng là một thủ tục lấy từ Cổng DVC Quốc gia.

Dữ liệu kỳ vọng hiện tại:

- Tổng active: `2154`
- Thủ tục thường: `2151`
- Thủ tục liên thông: `3`

Các cột chính:

| Cột | Ý nghĩa |
| --- | --- |
| `id` | UUID nội bộ |
| `source_id` | ID chi tiết trên Cổng DVCQG, dùng trong `ma_thu_tuc=...` |
| `procedure_code` | Mã thủ tục hiển thị |
| `procedure_group` | `administrative` hoặc `interlinked` |
| `name` | Tên thủ tục |
| `target_audience` | Đối tượng thực hiện |
| `field_name` | Lĩnh vực |
| `published_agency` | Cơ quan ban hành |
| `implementation_agency` | Cơ quan thực hiện |
| `implementation_level` | Cấp thực hiện |
| `execution_methods` | JSON cách thức nộp: trực tiếp, trực tuyến, bưu chính |
| `execution_steps` | Trình tự thực hiện |
| `required_documents` | Thành phần hồ sơ |
| `processing_time` | Thời hạn giải quyết |
| `fees` | Phí/lệ phí |
| `requirements` | Yêu cầu, điều kiện |
| `legal_basis` | Căn cứ pháp lý |
| `attachments` | JSON biểu mẫu/file đính kèm nếu lấy được |
| `related_procedures` | JSON thủ tục liên quan nếu có |
| `source_url` | Link nguồn |
| `raw_summary` | JSON dữ liệu thô từ danh sách |
| `raw_detail` | JSON dữ liệu thô từ chi tiết |
| `content_hash` | Hash nội dung để phát hiện thay đổi |
| `is_active` | Soft delete, không xóa cứng |
| `last_seen_at` | Lần gần nhất crawler thấy thủ tục |
| `source_updated_at` | Ngày cập nhật từ nguồn nếu có |
| `created_at` | Thời điểm insert |
| `updated_at` | Thời điểm update |

Ràng buộc:

- Unique theo `(procedure_code, procedure_group)`.
- Nếu nguồn không còn trả thủ tục, hệ thống đánh dấu `is_active=false`, không xóa cứng.

Index:

- `procedure_group`
- `is_active`
- `field_name`
- `implementation_agency`
- `last_seen_at`
- GIN trigram trên `name`

## 3. `procedure_embeddings`

Bảng vector search bằng Supabase pgvector.

Dữ liệu kỳ vọng hiện tại:

- Tổng vector active: `2154`
- Embedding model: `gemini-embedding-001`
- Dimension: `768`
- Distance: cosine

Các cột chính:

| Cột | Ý nghĩa |
| --- | --- |
| `id` | UUID dòng embedding |
| `procedure_id` | FK tới `procedures.id` |
| `procedure_code` | Mã thủ tục |
| `procedure_group` | `administrative` hoặc `interlinked` |
| `name` | Tên thủ tục |
| `field_name` | Lĩnh vực |
| `target_audience` | Đối tượng |
| `source_url` | Link nguồn |
| `embedding_model` | Model tạo embedding |
| `embedding_dim` | Số chiều, hiện là `768` |
| `embedding` | Vector pgvector |
| `content_hash` | Hash nội dung tại lúc tạo embedding |
| `is_active` | Trạng thái active |
| `created_at` | Thời điểm tạo |
| `updated_at` | Thời điểm cập nhật |

Text tạo embedding gồm tên, mã, nhóm, lĩnh vực, đối tượng và cơ quan thực hiện.

Index vector:

```sql
using hnsw (embedding vector_cosine_ops)
```

RPC search:

```sql
public.match_procedure_embeddings(
  query_embedding vector(768),
  match_count int,
  filter_group text,
  filter_target_audience text
)
```

Similarity được tính bằng:

```sql
1 - (embedding <=> query_embedding)
```

## 4. `procedure_versions`

Lưu snapshot lịch sử khi crawler insert hoặc update thủ tục.

| Cột | Ý nghĩa |
| --- | --- |
| `id` | UUID version |
| `procedure_id` | FK tới thủ tục hiện tại |
| `procedure_code` | Mã thủ tục |
| `procedure_group` | Nhóm thủ tục |
| `content_hash` | Hash nội dung version |
| `payload` | JSON snapshot đầy đủ |
| `created_at` | Thời điểm ghi version |

Mục đích:

- Audit thay đổi.
- Debug crawler.
- So sánh version cũ/mới trong tương lai.

## 5. `crawl_runs`

Lưu log mỗi lần crawler chạy.

| Cột | Ý nghĩa |
| --- | --- |
| `id` | UUID run |
| `source_name` | Tên nguồn, hiện là `dvcqg` |
| `procedure_group` | Nhóm crawl |
| `status` | `running`, `success`, `failed` |
| `started_at` | Bắt đầu |
| `finished_at` | Kết thúc |
| `total_seen` | Tổng thủ tục thấy được |
| `inserted_count` | Số insert |
| `updated_count` | Số update |
| `unchanged_count` | Số không đổi |
| `inactivated_count` | Số đánh dấu inactive |
| `error_message` | Lỗi tổng |
| `metadata` | JSON bổ sung |

Lệnh liên quan:

```powershell
python -m app.cli sync --group administrative --full --mark-inactive
python -m app.cli sync --group interlinked --full --mark-inactive
```

## 6. `procedure_attachments`

Bảng dự phòng để tách file biểu mẫu/đính kèm ra khỏi JSON `procedures.attachments`.

Hiện tại crawler chủ yếu lưu attachments trong `procedures.attachments`.

| Cột | Ý nghĩa |
| --- | --- |
| `id` | UUID file |
| `procedure_id` | FK tới `procedures.id` |
| `title` | Tên file |
| `file_url` | Link file |
| `file_type` | Loại file |
| `source_payload` | JSON thô |
| `created_at` | Thời điểm lưu |

## 7. `vector_sync_logs`

Bảng này có từ migration đầu nhưng pipeline pgvector hiện tại chưa dùng.

Vector thật nằm ở:

```text
procedure_embeddings
```

Vì vậy `vector_sync_logs` trống không phải lỗi.

## 8. `chat_sessions`

Bảng lưu phiên chat khi người dùng đăng nhập Google qua Supabase Auth.

Sau migration `0003_chat_auth.sql`, bảng có thêm:

| Cột | Ý nghĩa |
| --- | --- |
| `user_id` | FK tới `auth.users(id)` |

Các cột chính:

| Cột | Ý nghĩa |
| --- | --- |
| `id` | UUID session |
| `user_id` | User sở hữu session |
| `user_type` | `individual` hoặc `business` |
| `initial_question` | Câu hỏi đầu tiên |
| `procedure_context` | JSON tối đa 3 thủ tục đang dùng làm context |
| `created_at` | Thời điểm tạo |
| `updated_at` | Thời điểm cập nhật |

Nếu user không đăng nhập:

- Backend vẫn trả lời chat.
- Không insert `chat_sessions`.
- Session dạng `local:...` chỉ tồn tại ở frontend hiện tại.

Lưu trữ:

- Chat session tự xóa sau 7 ngày nếu không có tin nhắn mới.
- Mỗi tin nhắn mới cập nhật `updated_at`, từ đó gia hạn thời điểm tự xóa thêm 7 ngày.

## 9. `chat_messages`

Bảng lưu từng message trong session đã đăng nhập.

| Cột | Ý nghĩa |
| --- | --- |
| `id` | UUID message |
| `session_id` | FK tới `chat_sessions.id` |
| `role` | `user`, `assistant`, `system` |
| `content` | Nội dung |
| `metadata` | JSON metadata |
| `created_at` | Thời điểm gửi |

Khi tiếp tục chat, backend lấy `chat_sessions.procedure_context` và chỉ dùng context đó để trả lời.

## 10. Auth Và RLS

RLS đang bật cho các bảng chính.

Public read:

- `procedures` nếu `is_active=true`
- `procedure_attachments` nếu thủ tục cha active

Chat auth:

- Supabase Auth Google dùng JWT.
- Frontend đăng nhập Google qua Supabase Auth.
- Backend đọc JWT từ header `Authorization: Bearer ...`.
- Backend gắn `chat_sessions.user_id` khi lưu session.
- API lịch sử chat chỉ trả session của user đang đăng nhập.

Policy trong `0003_chat_auth.sql`:

```sql
auth.uid() = user_id
```

cho `chat_sessions`, và `chat_messages` đọc qua session cha.

Backend vẫn dùng `SUPABASE_SERVICE_ROLE_KEY` server-side. Không đưa service role key lên frontend.

## 11. Quan Hệ Bảng

```text
procedures
  1 -> n procedure_versions
  1 -> n procedure_attachments
  1 -> 1 procedure_embeddings

auth.users
  1 -> n chat_sessions

chat_sessions
  1 -> n chat_messages

crawl_runs
  độc lập, log mỗi lần crawl

vector_sync_logs
  hiện chưa dùng trong pipeline chính
```

## 12. API Liên Quan

Public/data:

```text
GET  /api/health
GET  /api/auth/supabase-config
GET  /api/procedures
GET  /api/procedures/{procedure_id}
GET  /api/filters
GET  /api/stats/overview
POST /api/search/vector
```

Chat:

```text
POST  /api/chat/sessions
GET   /api/chat/sessions
GET   /api/chat/sessions/{session_id}
POST  /api/chat/sessions/{session_id}/messages
PATCH /api/chat/sessions/{session_id}/context
POST  /api/chat/context/summarize
POST  /api/chat/local/messages
```

Crawler preview:

```text
GET /api/crawler/preview
```

## 13. Chatbot Flow Hiện Tại

Câu hỏi đầu tiên:

```text
user_type + question
  -> LLM đoán tối đa 3 tên thủ tục
  -> với mỗi tên, pgvector lấy 2 thủ tục gần nhất
  -> deduplicate theo mã thủ tục + nhóm
  -> sort theo similarity
  -> giữ tối đa 3 thủ tục
  -> Gemini tóm tắt song song bằng pool API keys
  -> lưu procedure_context nếu user đã login
  -> trả lời tiếng Việt, kèm mã thủ tục và link nguồn
```

Câu hỏi tiếp theo:

```text
message mới
  -> dùng procedure_context hiện tại
  -> không search lại nếu context vẫn phù hợp
  -> nếu vượt context, AI nói rõ và hỏi có muốn tìm thủ tục khác không
```

Context editor:

- Tối đa 3 thủ tục.
- Có thể xóa thủ tục khỏi context.
- Có thể tìm thủ tục bằng pgvector rồi thêm vào context.
- Khi thêm, backend đọc/tóm tắt thủ tục tương tự pipeline ban đầu.

## 14. Thống Kê

Thống kê hiện có:

- Tổng số thủ tục.
- Số thủ tục thường/liên thông.
- Số thủ tục theo lĩnh vực.
- Số thủ tục theo cơ quan.
- Thủ tục mới cập nhật gần đây.

## 15. Lệnh Kiểm Tra Nhanh

Chạy trong `apps/api`:

```powershell
python -m app.cli db-count --group all
python -m app.cli vector-count --group all
python -m app.cli vector-search "xin giấy phép kinh doanh karaoke" --limit 5
python -m app.cli llm-test
```

Sync crawler:

```powershell
python -m app.cli sync --group administrative --full --mark-inactive
python -m app.cli sync --group interlinked --full --mark-inactive
```

Sync embedding:

```powershell
python -m app.cli vector-sync --group all --full
```

Rebuild embedding:

```powershell
python -m app.cli vector-sync --group all --full --force
```
