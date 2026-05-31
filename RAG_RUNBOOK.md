# RAG_RUNBOOK.md

Huong dan chay pipeline RAG moi sau khi code da duoc cap nhat.

## 1. Can Dien Trong `.env`

Kiem tra/cap nhat cac bien sau trong file `.env` o root project:

```text
VECTOR_STORE=pinecone

PINECONE_API_KEY=...
PINECONE_INDEX_NAME=hcm-govbot
PINECONE_NAMESPACE=dev
PINECONE_METRIC=cosine

EMBEDDING_PROVIDER=huggingface
HF_TOKEN=
HF_EMBEDDING_MODEL=AITeamVN/Vietnamese_Embedding
HF_EMBEDDING_DEVICE=cpu
HF_EMBEDDING_BATCH_SIZE=16

RERANKER_ENABLED=true
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RERANKER_DEVICE=cpu
RETRIEVAL_RERANK_TOP_N=8

BM25_TOKENIZER=underthesea
BM25_CACHE_PATH=.rag_cache/bm25_cache.pkl
BM25_ALLOW_LIVE_BUILD=false
CHUNK_TOKEN_LIMIT=512
CHUNK_OVERLAP_TOKENS=50
```

Neu may co GPU va da cai torch CUDA dung phien ban, co the doi:

```text
HF_EMBEDDING_DEVICE=cuda
RERANKER_DEVICE=cuda
```

## 2. Chay Migration Supabase

Chay file sau trong Supabase SQL Editor:

```text
supabase/migrations/0004_rag_pipeline.sql
```

Buoc nay them:

- `procedure_documents`
- `procedure_chunks`
- `retrieval_eval_questions`
- `retrieval_eval_results`
- `rag_eval_results`
- `chat_sessions.source_context`

## 3. Cai Dependency RAG

Lenh nay co the lau vi tai `torch`, `sentence-transformers`, model tokenizer va underthesea:

```powershell
cd D:\HOC_KI_6\Hcm-GovBot\apps\api
pip install -r requirements-rag.txt
```

Python `textract` duoc tach rieng vi package nay co dependency cu. Chi cai neu can fallback textract that su:

```powershell
pip install -r requirements-textract.txt
```

## 4. Build Documents Va Chunks

Chay thu nho truoc:

```powershell
cd D:\HOC_KI_6\Hcm-GovBot\apps\api
python -m app.cli rag-build --limit 5 --force
```

Neu OK, build toan bo:

```powershell
python -m app.cli rag-build --full --force
```

Buoc nay ghi du lieu vao Supabase:

- HTML/structured data -> markdown trong `procedure_documents`
- parent-child chunks trong `procedure_chunks`

## 5. Sync Chunks Len Pinecone

Chay thu nho truoc:

```powershell
python -m app.cli pinecone-sync --limit 20 --batch-size 8
```

Neu OK, sync toan bo:

```powershell
python -m app.cli pinecone-sync --full --batch-size 32
```

Buoc nay co the lau vi:

- lan dau se tai model `AITeamVN/Vietnamese_Embedding`;
- embed tat ca chunks;
- upload vector len Pinecone namespace `dev`.

## 6. Test Retrieval

Truoc khi test/chat, build BM25 cache de request khong phai tokenize lai 19k chunks bang `underthesea`:

```powershell
python -m app.cli bm25-build-cache
```

Sau khi sync Pinecone va build BM25 cache:

```powershell
python -m app.cli hybrid-search "toi muon xin giay phep kinh doanh karaoke" --limit 8
```

Ky vong ket qua co:

- `chunk_id`
- `procedure_code`
- `name`
- `section_name`
- `rerank_score`
- `preview`

## 7. Chay Backend Va Frontend

Backend:

```powershell
cd D:\HOC_KI_6\Hcm-GovBot\apps\api
python -m app.main
```

Frontend:

```powershell
cd D:\HOC_KI_6\Hcm-GovBot\apps\web
npx vite --host 127.0.0.1
```

Mo:

```text
http://127.0.0.1:5173
```

## 8. Evaluation Retrieval

Sau khi tao va review 100 cau trong `retrieval_eval_questions`, chay:

```powershell
cd D:\HOC_KI_6\Hcm-GovBot\apps\api
python -m app.cli eval-retrieval --run-name rag-v1 --k 8 --save
```

Neu muon test ca cau chua review:

```powershell
python -m app.cli eval-retrieval --run-name rag-v1-draft --k 8 --include-unreviewed
```

## 9. Scheduler Tu Dong Cap Nhat

Scheduler co the tu dong chay pipeline:

```text
crawl DVCQG
  -> update Supabase procedures
  -> rag-build procedure_documents/procedure_chunks
  -> pinecone-sync vectors
  -> bm25-build-cache neu SCHEDULER_BM25_SYNC_ENABLED=true
```

Bat trong `.env`:

```text
SCHEDULER_ENABLED=true
SCHEDULER_INTERVAL_HOURS=24
SCHEDULER_RUN_ON_STARTUP=false
SCHEDULER_RAG_SYNC_ENABLED=true
SCHEDULER_BM25_SYNC_ENABLED=false
SCHEDULER_PINECONE_BATCH_SIZE=32
SCHEDULER_RAG_PROGRESS_EVERY=100
```

Luu y:

- Neu `SCHEDULER_RUN_ON_STARTUP=true`, backend se chay pipeline sau khi start vai giay. Pipeline co the rat lau vi Pinecone embedding local.
- Render free 512MB RAM khong nen build BM25 cache trong scheduler. Giu `SCHEDULER_BM25_SYNC_ENABLED=false`.
- Neu chi muon crawl vao Supabase ma khong update RAG/Pinecone, de `SCHEDULER_RAG_SYNC_ENABLED=false`.
- Neu co may/plan du RAM va bat `SCHEDULER_BM25_SYNC_ENABLED=true`, scheduler se build lai BM25 cache va refresh BM25 trong RAM cho cac cau hoi sau.

## 10. Cac Loi Thuong Gap

Neu backend bao thieu Pinecone key:

```text
Missing PINECONE_API_KEY in .env
```

=> Dien `PINECONE_API_KEY`.

Neu bao thieu dependency:

```text
Missing sentence-transformers / rank-bm25 / underthesea / pinecone SDK
```

=> Chay `pip install -r requirements-rag.txt`.

Neu hybrid search khong co ket qua:

- Kiem tra da chay migration `0004_rag_pipeline.sql`.
- Kiem tra `rag-build --full --force` da tao `procedure_chunks`.
- Kiem tra `pinecone-sync --full` da upload vector len dung namespace.
- Kiem tra `PINECONE_INDEX_NAME` va `PINECONE_NAMESPACE` trong `.env`.
