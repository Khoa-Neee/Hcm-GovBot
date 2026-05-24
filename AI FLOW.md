# AI FLOW.md

Tài liệu này mô tả luồng AI của HCM GovBot khi người dùng hỏi về thủ tục hành chính.

## 1. Mục Tiêu

AI không chỉ liệt kê các thủ tục gần đúng. Mục tiêu hiện tại là:

- Hiểu câu hỏi của người dùng.
- Tìm tối đa 3 thủ tục liên quan nhất.
- Tóm tắt đúng phần dữ liệu cần thiết từ các thủ tục đó.
- Trả lời trực tiếp vào nhu cầu của người dùng bằng tiếng Việt dễ hiểu.
- Giữ context nhỏ, rõ, và có thể hỏi tiếp trong cùng phiên.

## 2. Câu Hỏi Đầu Tiên

Khi người dùng gửi câu hỏi đầu tiên, frontend gọi:

```text
POST /api/chat/sessions
```

Payload chính:

```json
{
  "user_type": "individual",
  "question": "..."
}
```

Backend xử lý trong `ChatService.start_session`.

### Bước 1: Đoán tên thủ tục có thể liên quan

Backend gọi Gemini để suy luận tối đa 3 tên thủ tục hành chính có khả năng liên quan nhất từ câu hỏi.

Ví dụ người dùng hỏi:

```text
Tôi muốn nhận nuôi con nuôi thì cần giấy tờ gì?
```

AI có thể suy ra các tên thủ tục gần đúng như:

```text
Đăng ký việc nuôi con nuôi trong nước
Đăng ký lại việc nuôi con nuôi
Giải quyết việc nuôi con nuôi có yếu tố nước ngoài
```

### Bước 2: Tìm thủ tục bằng pgvector

Với mỗi tên thủ tục đã đoán, backend gọi vector search:

```text
SupabaseVectorService.search
```

Mỗi query tìm một số thủ tục gần nhất trong bảng:

```text
procedure_embeddings
```

Sau đó backend:

- Gộp kết quả trùng theo mã thủ tục và nhóm thủ tục.
- Sắp xếp theo `similarity`.
- Chỉ giữ tối đa 3 thủ tục tốt nhất.

Giới hạn 3 thủ tục giúp câu trả lời tập trung hơn và tránh context quá nhiễu.

### Bước 3: Lấy chi tiết thủ tục từ database

Backend lấy bản ghi đầy đủ trong bảng:

```text
procedures
```

Các trường quan trọng được dùng cho AI gồm:

- Tên thủ tục.
- Mã thủ tục.
- Lĩnh vực.
- Cơ quan thực hiện.
- Đối tượng.
- Cách thức thực hiện.
- Thành phần hồ sơ.
- Trình tự thực hiện.
- Thời hạn.
- Phí/lệ phí.
- Yêu cầu, điều kiện.
- Căn cứ pháp lý.
- Link nguồn.

## 3. Tóm Tắt Từng Thủ Tục

Backend gọi Gemini song song để tóm tắt từng thủ tục trong tối đa 3 thủ tục đã chọn.

Mỗi lần tóm tắt sử dụng prompt yêu cầu:

- Chỉ dùng dữ liệu thật trong database.
- Không bịa thông tin ngoài dữ liệu.
- Tập trung vào câu hỏi của người dùng.
- Ưu tiên hồ sơ, thời hạn, phí/lệ phí, cơ quan thực hiện và cách nộp nếu liên quan.
- Luôn giữ mã thủ tục và link nguồn.

Kết quả tóm tắt được lưu thành `procedure_context`.

## 4. Trả Lời Câu Đầu

Sau khi có các tóm tắt, backend gọi Gemini lần nữa để tạo câu trả lời cuối.

Yêu cầu quan trọng:

- Trả lời trực tiếp câu hỏi của người dùng.
- Không mở đầu bằng danh sách toàn bộ thủ tục phù hợp.
- Nếu có một thủ tục phù hợp rõ nhất, dùng thủ tục đó làm câu trả lời chính.
- Nếu có nhiều trường hợp dễ nhầm, chỉ nêu ngắn gọn điều kiện phân biệt.
- Luôn kèm mã thủ tục và link nguồn của thủ tục đang dùng.

Ví dụ định hướng câu trả lời:

```text
Nếu bạn muốn nhận nuôi con nuôi trong nước, thủ tục chính là Đăng ký việc nuôi con nuôi trong nước.

- Hồ sơ cần chuẩn bị: ...
- Cơ quan thực hiện: ...
- Thời hạn giải quyết: ...
- Lệ phí: ...
- Mã thủ tục: ...
- Link nguồn: ...
```

## 5. Lưu Phiên Chat

Nếu người dùng đã đăng nhập Google, backend lưu phiên chat vào Supabase:

```text
chat_sessions
chat_messages
```

Trong `chat_sessions`, backend lưu:

- `user_id`
- `user_type`
- `initial_question`
- `procedure_context`
- `created_at`
- `updated_at`

Trong `chat_messages`, backend lưu:

- Tin nhắn người dùng.
- Câu trả lời AI.
- Metadata như `inference_seconds` và danh sách thủ tục trong context.

Nếu người dùng chưa đăng nhập, chat vẫn hoạt động nhưng không lưu lịch sử vào database.

## 6. Hạn Lưu 7 Ngày

Chat đã đăng nhập chỉ được giữ trong 7 ngày kể từ lần hỏi gần nhất.

Cơ chế:

- Mỗi khi người dùng gửi tin nhắn mới, backend cập nhật `updated_at` của session.
- `expires_at` được tính là `updated_at + 7 ngày`.
- Khi list, mở, hoặc xử lý chat session, backend dọn các session có `updated_at` cũ hơn 7 ngày.
- Scheduler cũng gọi dọn session quá hạn trong pipeline định kỳ.

Frontend hiển thị thời điểm tự xóa để người dùng biết.

## 7. Câu Hỏi Tiếp Theo

Khi người dùng hỏi tiếp trong cùng phiên, frontend gọi:

```text
POST /api/chat/sessions/{session_id}/messages
```

Backend xử lý trong `ChatService.continue_session`.

Luồng xử lý:

```text
message mới
  -> lấy procedure_context hiện tại
  -> chỉ dùng tối đa 3 thủ tục trong context
  -> gọi Gemini trả lời dựa trên context
  -> không search lại mặc định
  -> lưu tin nhắn nếu đã đăng nhập
  -> cập nhật updated_at để gia hạn thêm 7 ngày
```

Nếu câu hỏi mới vượt khỏi context, AI được yêu cầu nói rõ nội dung có vẻ nằm ngoài các thủ tục đang xét và hỏi người dùng có muốn tìm thủ tục khác không.

## 8. Thêm/Xóa Thủ Tục Trong Context

Người dùng có thể tìm thủ tục ở panel bên phải để thêm vào context.

Luồng thêm thủ tục:

```text
Người dùng nhập từ khóa
  -> frontend gọi vector search
  -> hiển thị kết quả gần đúng
  -> người dùng bấm Thêm
  -> backend lấy chi tiết thủ tục
  -> Gemini tóm tắt thủ tục theo câu hỏi/context hiện tại
  -> thêm vào procedure_context
```

Giới hạn:

```text
Tối đa 3 thủ tục trong context
```

Nếu context đã đủ 3 thủ tục, người dùng phải xóa bớt một thủ tục trước khi thêm thủ tục mới.

## 9. Thời Gian Suy Luận

Backend đo thời gian xử lý bằng `time.perf_counter`.

Các API chat trả thêm:

```json
{
  "inference_seconds": 12.34
}
```

Frontend hiển thị dưới câu trả lời:

```text
Thời gian suy luận: 12,3 giây
```

Với phiên đã lưu, thời gian suy luận cũng được lưu trong metadata của message assistant.

## 10. Các Thành Phần Chính

Backend:

```text
apps/api/app/services/chat_service.py
apps/api/app/services/supabase_vector_service.py
apps/api/app/services/supabase_repo.py
apps/api/app/api.py
```

Frontend:

```text
apps/web/src/App.tsx
apps/web/src/api.ts
```

Database:

```text
procedures
procedure_embeddings
chat_sessions
chat_messages
```

## 11. Tóm Tắt Luồng Tổng Quát

```text
Người dùng hỏi
  -> Gemini đoán tên thủ tục
  -> pgvector tìm thủ tục gần nhất
  -> giữ tối đa 3 thủ tục
  -> lấy chi tiết từ Supabase
  -> Gemini tóm tắt từng thủ tục
  -> Gemini trả lời trực tiếp câu hỏi
  -> lưu session/message nếu đã đăng nhập
  -> frontend hiển thị câu trả lời, context, thời gian suy luận, hạn tự xóa
```

