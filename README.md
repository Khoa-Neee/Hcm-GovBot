# HCM GovBot

Web app tra cứu, thống kê và hỏi đáp thủ tục hành chính công cho người dân Thành phố Hồ Chí Minh.

## Stack

- Frontend: React + TypeScript + TailwindCSS + Vite
- Backend: Python FastAPI
- Database: Supabase PostgreSQL
- Vector search: Supabase PostgreSQL + pgvector
- Chat model: `gemini-2.5-flash-lite` qua Gemini API
- Embedding model: `gemini-embedding-001`

FastAPI được dùng cho crawler, normalize dữ liệu, embedding sync, job scheduler và gọi LLM.

## Model LLM

Backend đang dùng model chat:

```txt
GEMINI_CHAT_MODEL=gemini-2.5-flash-lite
```

Model embedding vẫn tách riêng:

```txt
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=768
```

Kiểm tra nhanh Gemini sau khi điền key:

```bash
cd apps/api
python -m app.cli llm-test
```

Override model tạm thời nếu cần:

```bash
python -m app.cli llm-test --model gemini-2.5-flash-lite
```

## Tính Năng Chính

- Tra cứu thủ tục hành chính công Thành phố Hồ Chí Minh.
- Xem chi tiết thủ tục, hồ sơ cần chuẩn bị, trình tự thực hiện, yêu cầu điều kiện, căn cứ pháp lý.
- Thống kê dữ liệu thủ tục.
- Hỏi AI dựa trên tối đa 3 thủ tục liên quan nhất.
- Lưu lịch sử chat 7 ngày cho người dùng đăng nhập Google.
- Scheduler backend crawl/cập nhật database mỗi 24 giờ.

## Cấu Trúc Dự Án

```txt
apps/api                 FastAPI backend
apps/web                 React/Vite frontend
supabase/migrations      SQL schema và pgvector migrations
AI FLOW.md               Mô tả luồng AI trả lời câu hỏi
STATUS.md                Trạng thái triển khai hiện tại
SCHEMA.md                Ghi chú schema dữ liệu
```

## Chuẩn Bị Trước Khi Push GitHub

1. Không commit file `.env`.
2. Nếu key thật từng bị dán vào chat hoặc commit nhầm, hãy rotate lại key trước khi deploy.
3. Kiểm tra `.gitignore` đã có các dòng này:

```txt
.env
.env.*
node_modules/
dist/
__pycache__/
*.py[cod]
```

4. Nếu đã lỡ track file nhạy cảm, gỡ khỏi git index:

```bash
git rm --cached .env
```

## Biến Môi Trường Local

Tạo file `.env` ở root project. Không commit file này.

```txt
# Supabase
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Gemini
GEMINI_API_KEY_1=your-gemini-key
GEMINI_API_KEY_2=
GEMINI_API_KEY_3=
GEMINI_API_KEY_4=
GEMINI_API_KEY_5=
GEMINI_API_KEY_6=
GEMINI_API_KEY_7=
GEMINI_API_KEY_8=
GEMINI_API_KEY_9=
GEMINI_API_KEY_10=
GEMINI_CHAT_MODEL=gemini-2.5-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=768

# Data source
DVC_BASE_URL=https://thutuc.dichvucong.gov.vn
DVC_REST_PATH=/jsp/rest.jsp
DVC_HCMC_AGENCY_ID=411312
DVC_HCMC_AGENCY_NAME=UBND Thành phố Hồ Chí Minh
DVC_HCMC_AGENCY_CODE=H29
DVC_REQUEST_TIMEOUT_SECONDS=60
DVC_MAX_RETRIES=5
DVC_RETRY_BACKOFF_SECONDS=1.5
DVC_PAGE_DELAY_SECONDS=0.5

# Backend local
API_HOST=127.0.0.1
API_PORT=8000
API_RELOAD=false
BACKEND_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Vector search
VECTOR_STORE=supabase

# Scheduler
SCHEDULER_ENABLED=true
SCHEDULER_INTERVAL_HOURS=24
SCHEDULER_RUN_ON_STARTUP=true
SCHEDULER_STARTUP_DELAY_SECONDS=5
SCHEDULER_MARK_INACTIVE=true
SCHEDULER_VECTOR_FORCE=false

# Frontend local
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

Supabase URL phải là project root URL, không dùng `/rest/v1/`.

## Apply Supabase Schema

Vào Supabase Dashboard -> SQL Editor -> chạy lần lượt:

```txt
supabase/migrations/0001_initial_schema.sql
supabase/migrations/0002_pgvector_embeddings.sql
supabase/migrations/0003_chat_auth.sql
```

## Chạy Backend Local

Tạo môi trường Python:

```bash
conda create -n hcm-govbot python=3.11 -y
conda activate hcm-govbot
pip install -r requirements.txt
```

Chạy backend:

```bash
cd apps/api
python -m app.main
```

API local:

```txt
http://127.0.0.1:8000
http://127.0.0.1:8000/docs
```

Kiểm tra dữ liệu:

```bash
python -m app.cli db-count --group all
```

## Crawl Và Vector Sync

Preview nguồn:

```bash
cd apps/api
python -m app.cli crawl-preview --group administrative --limit 3
python -m app.cli crawl-preview --group interlinked --limit 3
```

Sync thử vài thủ tục:

```bash
python -m app.cli sync --group administrative --max-items 5
```

Sync full thủ tục thường Thành phố Hồ Chí Minh:

```bash
python -m app.cli sync --group administrative --full --mark-inactive --progress-every 25
```

Sync full thủ tục liên thông:

```bash
python -m app.cli sync --group interlinked --full --mark-inactive
```

Lưu ý: chỉ dùng `--mark-inactive` khi chạy `--full`. Không dùng `--mark-inactive` với `--max-items`.

Sync embedding:

```bash
python -m app.cli vector-sync --group all --full
```

Test semantic search:

```bash
python -m app.cli vector-search "tôi muốn xin giấy phép kinh doanh karaoke" --limit 5
```

Nếu muốn rebuild toàn bộ embedding:

```bash
python -m app.cli vector-sync --group all --full --force
```

## Chạy Frontend Local

```bash
cd apps/web
npm install
npm run dev
```

Frontend local:

```txt
http://localhost:5173
```

Build kiểm tra trước khi deploy:

```bash
npm run build
npm run lint
```

## Push Project Lên GitHub

1. Tạo repository mới trên GitHub, ví dụ `Hcm-GovBot`.

2. Mở terminal ở root project:

```bash
cd D:/HOC_KI_6/Hcm-GovBot
```

3. Khởi tạo git nếu project chưa có `.git`:

```bash
git init
```

4. Kiểm tra file sẽ được commit:

```bash
git status
```

Đảm bảo không có `.env`, `node_modules`, `dist`, `__pycache__`.

5. Add và commit:

```bash
git add .
git commit -m "Initial commit"
```

6. Gắn remote GitHub:

```bash
git branch -M main
git remote add origin https://github.com/<your-username>/Hcm-GovBot.git
```

Nếu remote đã tồn tại:

```bash
git remote set-url origin https://github.com/<your-username>/Hcm-GovBot.git
```

7. Push lên GitHub:

```bash
git push -u origin main
```

Các lần sau chỉ cần:

```bash
git add .
git commit -m "Update project"
git push
```

## Deploy Backend Lên Render

1. Vào Render -> New -> Web Service.
2. Chọn repository GitHub vừa push.
3. Cấu hình service:

```txt
Name: hcm-govbot-api
Root Directory: apps/api
Runtime: Python 3
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

4. Thêm Environment Variables trên Render:

```txt
PYTHON_VERSION=3.11.9
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

GEMINI_API_KEY_1=your-gemini-key
GEMINI_API_KEY_2=
GEMINI_API_KEY_3=
GEMINI_API_KEY_4=
GEMINI_API_KEY_5=
GEMINI_API_KEY_6=
GEMINI_API_KEY_7=
GEMINI_API_KEY_8=
GEMINI_API_KEY_9=
GEMINI_API_KEY_10=
GEMINI_CHAT_MODEL=gemini-2.5-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSIONS=768

DVC_BASE_URL=https://thutuc.dichvucong.gov.vn
DVC_REST_PATH=/jsp/rest.jsp
DVC_HCMC_AGENCY_ID=411312
DVC_HCMC_AGENCY_NAME=UBND Thành phố Hồ Chí Minh
DVC_HCMC_AGENCY_CODE=H29
DVC_REQUEST_TIMEOUT_SECONDS=60
DVC_MAX_RETRIES=5
DVC_RETRY_BACKOFF_SECONDS=1.5
DVC_PAGE_DELAY_SECONDS=0.5

VECTOR_STORE=supabase

SCHEDULER_ENABLED=true
SCHEDULER_INTERVAL_HOURS=24
SCHEDULER_RUN_ON_STARTUP=true
SCHEDULER_STARTUP_DELAY_SECONDS=5
SCHEDULER_MARK_INACTIVE=true
SCHEDULER_VECTOR_FORCE=false

BACKEND_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,https://your-vercel-domain.vercel.app
```

5. Deploy service.

6. Sau khi deploy xong, kiểm tra:

```txt
https://your-render-service.onrender.com/api/health
https://your-render-service.onrender.com/docs
```

Lưu ý: Render free instance có thể sleep, nên scheduler trong app có thể không chạy đúng giờ tuyệt đối. Khi cần ổn định hơn, dùng Render Cron Job hoặc GitHub Actions để gọi CLI/API theo lịch.

## Deploy Frontend Lên Vercel

1. Vào Vercel -> Add New -> Project.
2. Import repository GitHub.
3. Cấu hình project:

```txt
Framework Preset: Vite
Root Directory: apps/web
Install Command: npm install
Build Command: npm run build
Output Directory: dist
```

4. Thêm Environment Variables trên Vercel:

```txt
VITE_API_BASE_URL=https://your-render-service.onrender.com
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

5. Deploy frontend.

6. Sau khi có domain Vercel, quay lại Render và cập nhật:

```txt
BACKEND_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,https://your-vercel-domain.vercel.app
```

7. Redeploy backend trên Render để CORS nhận domain mới.

## Cấu Hình Google Login Sau Khi Deploy

Trong Supabase Dashboard:

1. Vào Authentication -> Providers -> Google.
2. Bật Google provider.
3. Điền Google Client ID và Client Secret.
4. Vào Authentication -> URL Configuration.
5. Đặt Site URL:

```txt
https://your-vercel-domain.vercel.app
```

6. Thêm Redirect URLs:

```txt
http://localhost:5173
https://your-vercel-domain.vercel.app
```

Trong Google Cloud Console, Authorized redirect URI thường là callback của Supabase:

```txt
https://your-project-ref.supabase.co/auth/v1/callback
```

Không đưa Google Client Secret vào Vercel hoặc frontend.

## Scheduler 24h

Backend có scheduler chạy nền. Khi `SCHEDULER_ENABLED=true`, backend sẽ tự crawl/cập nhật database sau khi start và tiếp tục chạy lại theo chu kỳ:

```txt
SCHEDULER_ENABLED=true
SCHEDULER_INTERVAL_HOURS=24
SCHEDULER_RUN_ON_STARTUP=true
SCHEDULER_STARTUP_DELAY_SECONDS=5
SCHEDULER_MARK_INACTIVE=true
SCHEDULER_VECTOR_FORCE=false
```

Pipeline scheduler chạy:

```txt
sync administrative full
sync interlinked full
vector-sync all
```

`SCHEDULER_RUN_ON_STARTUP=true` giúp lần cập nhật đầu chạy sau khi backend khởi động vài giây, thay vì phải chờ đủ 24 giờ. Scheduler có khóa nội bộ để nếu một lần crawl còn đang chạy thì lần kế tiếp sẽ bỏ qua.

## API Chính

```txt
GET  /api/health
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
POST /api/chat/local/messages
POST /api/chat/context/summarize
```

## Lỗi Thường Gặp

- `404 model not found`: kiểm tra `GEMINI_CHAT_MODEL=gemini-2.5-flash-lite` và API key Gemini.
- `403/429` từ Gemini: đổi key trong pool, chờ quota reset, hoặc giảm tần suất gọi.
- `403/429` từ nguồn DVCQG: tăng delay/backoff trong env.
- Supabase trả `401`: backend phải dùng `SUPABASE_SERVICE_ROLE_KEY` cho crawler/upsert.
- pgvector search lỗi `function match_procedure_embeddings does not exist`: chạy migration `0002_pgvector_embeddings.sql`.
- pgvector insert lỗi dimension: kiểm tra `EMBEDDING_DIMENSIONS=768` và migration dùng `vector(768)`.
- Frontend không gọi được API: kiểm tra `VITE_API_BASE_URL` trên Vercel và `BACKEND_CORS_ORIGINS` trên Render.
- Google login không quay về đúng trang: kiểm tra Supabase Redirect URLs có domain Vercel.
