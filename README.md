# HCM GovBot - Automated QA System for Administrative Procedures in HCMC

Web app tra cứu, thống kê và hỏi đáp thủ tục hành chính công cho người dân Thành phố Hồ Chí Minh.

**Demo:** https://hcm-gov-bot.vercel.app/

## Tính Năng

- Tra cứu thủ tục hành chính công Thành phố Hồ Chí Minh theo tên, mã thủ tục, lĩnh vực và cơ quan.
- Xem chi tiết thủ tục: cơ quan thực hiện, đối tượng, thời hạn, phí/lệ phí, hồ sơ, trình tự, yêu cầu điều kiện, căn cứ pháp lý và link nguồn.
- Thống kê tổng quan dữ liệu thủ tục theo lĩnh vực, cơ quan và nhóm thủ tục.
- Hỏi AI về thủ tục hành chính bằng tiếng Việt tự nhiên.
- AI trả lời dựa trên tối đa 3 thủ tục liên quan nhất, có mã thủ tục và link nguồn.
- Đăng nhập Google để lưu lịch sử chat; lịch sử tự xóa sau 7 ngày không hỏi thêm.
- Panel chỉnh context thủ tục dùng để trả lời: thêm/xóa thủ tục khi cần.
- Backend có scheduler crawl/cập nhật dữ liệu định kỳ 24 giờ.

## Tech Stack

Frontend:

- React
- TypeScript
- Vite
- TailwindCSS
- lucide-react
- Deploy: Vercel

Backend:

- Python
- FastAPI
- Uvicorn
- httpx
- BeautifulSoup
- APScheduler
- Deploy: Render

Database/Auth/AI:

- Supabase PostgreSQL
- Supabase Auth Google
- pgvector
- Gemini chat model: `gemini-2.5-flash-lite`
- Gemini embedding model: `gemini-embedding-001`

## Kiến Trúc

```txt
Cổng Dịch vụ công Quốc gia
  -> FastAPI crawler
  -> Supabase PostgreSQL
  -> Gemini embedding
  -> pgvector semantic search
  -> Gemini RAG chatbot
  -> React frontend
```

Luồng AI:

```txt
Người dùng hỏi
  -> Gemini đoán tên thủ tục liên quan
  -> pgvector tìm thủ tục gần nhất
  -> giữ tối đa 3 thủ tục
  -> lấy chi tiết từ Supabase
  -> Gemini tóm tắt context
  -> Gemini trả lời trực tiếp câu hỏi
```

## Cấu Trúc Dự Án

```txt
apps/api                 FastAPI backend
apps/web                 React/Vite frontend
supabase/migrations      Database schema và pgvector migrations
AI FLOW.md               Mô tả luồng AI
SCHEMA.md                Ghi chú database schema
STATUS.md                Trạng thái triển khai
```

## Chạy Local

Backend:

```bash
conda create -n hcm-govbot python=3.11 -y
conda activate hcm-govbot
pip install -r requirements.txt
cd apps/api
python -m app.main
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

URL local:

```txt
Backend:  http://127.0.0.1:8000
Swagger:  http://127.0.0.1:8000/docs
Frontend: http://localhost:5173
```

## Environment Variables

Các biến chính cần có trong `.env` hoặc trên Render/Vercel:

```txt
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

GEMINI_API_KEY_1=
GEMINI_CHAT_MODEL=gemini-2.5-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=768

BACKEND_CORS_ORIGINS=http://localhost:5173,https://hcm-gov-bot.vercel.app
VITE_API_BASE_URL=
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
```

Không commit `.env` hoặc bất kỳ API key nào.

## Deploy

Frontend deploy trên Vercel:

```txt
Root Directory: apps/web
Build Command: npm run build
Output Directory: dist
```

Backend deploy trên Render:

```txt
Root Directory: apps/api
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Vercel cần:

```txt
VITE_API_BASE_URL=https://your-render-service.onrender.com
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

Render cần thêm domain Vercel vào CORS:

```txt
BACKEND_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,https://hcm-gov-bot.vercel.app
```

## Database

Chạy các migration trong Supabase SQL Editor:

```txt
supabase/migrations/0001_initial_schema.sql
supabase/migrations/0002_pgvector_embeddings.sql
supabase/migrations/0003_chat_auth.sql
```

Bảng chính:

- `procedures`
- `procedure_embeddings`
- `procedure_versions`
- `crawl_runs`
- `chat_sessions`
- `chat_messages`

## Ghi Chú

- Dữ liệu được crawl từ Cổng Dịch vụ công Quốc gia và lọc theo Thành phố Hồ Chí Minh.
- Vector search dùng pgvector với cosine similarity.
- Chatbot dùng mô hình RAG để giảm hallucination và giữ câu trả lời bám dữ liệu nguồn.
- Render free instance có thể sleep, nên scheduler 24h không đảm bảo chạy đúng giờ tuyệt đối trên free tier.
