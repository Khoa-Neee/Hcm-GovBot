# AI FLOW.md

Tai lieu nay mo ta luong AI/RAG hien tai cua HCM GovBot sau khi chuyen sang parent-child chunking, Pinecone, BM25, RRF va reranker.

## 1. Muc Tieu

Muc tieu cua AI la tra loi dung cau hoi cua nguoi dung dua tren du lieu thu tuc hanh chinh TP.HCM da crawl.

Yeu cau chinh:

- Tra loi truc tiep vao cau hoi, khong liet ke tran lan toan bo thu tuc.
- Chi dua tren context duoc retrieve tu du lieu that.
- Neu khong co thong tin trong context, noi ro chua thay du lieu.
- Moi thong tin quan trong can co citation dang `[C1]`, `[C2]`.
- UI hien thi cac chunk nguon da dung de nguoi dung kiem tra.
- Cau hoi tiep theo khong bi khoa vao context cu; he thong se phan loai follow-up/topic moi va retrieve lai.

## 2. Cac Noi Luu Tru Du Lieu

He thong hien tai ket hop 3 lop luu tru:

```text
Supabase PostgreSQL
  -> du lieu goc, markdown, chunks, chat history, evaluation

Pinecone
  -> vector embedding cua procedure_chunks

Local cache file
  -> BM25 lexical index cache
```

### Supabase

Supabase la database chinh cua ung dung.

Bang quan trong:

```text
procedures
procedure_documents
procedure_chunks
chat_sessions
chat_messages
retrieval_eval_questions
retrieval_eval_results
rag_eval_results
```

Vai tro:

- `procedures`: thu tuc goc da crawl tu Cong DVCQG.
- `procedure_documents`: noi dung thu tuc da chuan hoa thanh markdown.
- `procedure_chunks`: child chunks 512 tokens, overlap 50 tokens.
- `chat_sessions`: phien chat cua user dang nhap, gom `procedure_context` va `source_context`.
- `chat_messages`: tin nhan user/assistant va metadata.
- `retrieval_eval_*`, `rag_eval_results`: du lieu danh gia retrieval/RAG.

### Pinecone

Pinecone luu vector cua tung chunk trong `procedure_chunks`.

Moi vector dung:

```text
id = chunk_id
values = embedding cua chunk
metadata = procedure_id, procedure_code, name, section_name, source_url, ...
namespace = dev/prod
metric = cosine
dimension = 1024
```

Pinecone khong phai noi luu du lieu day du. No dung de semantic search nhanh. Sau khi Pinecone tra ve `chunk_id`, backend lay noi dung chunk day du tu Supabase.

### BM25 Cache File

BM25 dung de lexical search theo keyword tieng Viet.

Vi tokenize 19k chunks bang `underthesea` rat cham, backend dung cache file:

```text
.rag_cache/bm25_cache.pkl
```

Cache nay duoc tao thu cong bang:

```powershell
python -m app.cli bm25-build-cache
```

Khi chat runtime, BM25 load tu cache thay vi tokenize lai toan bo chunks.

## 3. Pipeline Tao Du Lieu RAG

### Buoc 1: Crawl va luu thu tuc goc

Crawler lay du lieu tu Cong DVCQG va luu vao:

```text
procedures
```

Lenh lien quan:

```powershell
python -m app.cli sync --group administrative --full --mark-inactive
python -m app.cli sync --group interlinked --full --mark-inactive
```

### Buoc 2: Chuan hoa markdown va chunking

Lenh:

```powershell
python -m app.cli rag-build --full --force
```

Luong xu ly:

```text
procedures
  -> DocumentExtractionService
  -> procedure_documents.normalized_markdown
  -> ChunkingService
  -> procedure_chunks
```

`DocumentExtractionService`:

- Lay metadata thu tuc.
- Lay cac section: cach thuc thuc hien, thoi han, phi/le phi, ho so, trinh tu, yeu cau, can cu phap ly.
- Parse HTML table thanh markdown table neu co.
- Python `textract` chi la fallback tuy chon; phase hien tai uu tien HTML/structured fields.

`ChunkingService`:

- Chunk theo section truoc.
- Child chunk gioi han 512 tokens.
- Overlap 50 tokens.
- Moi chunk co header ngu canh:

```text
Thu tuc: ...
Ma thu tuc: ...
Linh vuc: ...
Co quan thuc hien: ...
Muc: ...
```

### Buoc 3: Embed va upsert Pinecone

Lenh:

```powershell
python -m app.cli pinecone-sync --full --batch-size 32
```

Luong xu ly:

```text
procedure_chunks
  -> HuggingFaceEmbeddingService
  -> AITeamVN/Vietnamese_Embedding
  -> vector 1024 dimensions
  -> Pinecone upsert theo chunk_id
```

`upsert` nghia la:

- Chua co `chunk_id` thi insert.
- Da co `chunk_id` thi update/ghi de.
- Khong tao record trung.

### Buoc 4: Build BM25 cache

Lenh:

```powershell
python -m app.cli bm25-build-cache
```

Luong xu ly:

```text
procedure_chunks
  -> underthesea word_tokenize
  -> BM25 tokenized corpus
  -> .rag_cache/bm25_cache.pkl
```

Sau khi data thay doi, nen chay lai:

```text
rag-build -> pinecone-sync -> bm25-build-cache -> restart backend
```

## 4. Luong Chat Cau Hoi Dau Tien

Frontend goi:

```text
POST /api/chat/sessions
```

Payload:

```json
{
  "user_type": "individual",
  "question": "..."
}
```

Backend xu ly trong:

```text
ChatService.start_session
```

Luong chinh:

```text
question
  -> ChatRoutingService.route
  -> HybridRetrievalService.search
  -> ContextPackingService.pack
  -> Gemini answer generation
  -> response answer + sources
```

Voi cau hoi dau tien, route mac dinh la:

```text
new_topic
```

## 5. Hybrid Retrieval

Retrieval hien tai dung ket hop:

```text
BM25 lexical search
+ Pinecone dense vector search
+ RRF fusion
+ bge reranker
```

Luong:

```text
query
  -> BM25Service.search
  -> PineconeVectorService.search
  -> Reciprocal Rank Fusion
  -> lay full chunks tu Supabase
  -> RerankService.rerank
  -> top chunks
```

### BM25

BM25 tim theo keyword lexical.

Nguon:

```text
.rag_cache/bm25_cache.pkl
```

Neu cache chua co, backend co the build live tu Supabase, nhung viec nay rat cham. Nen luon build cache truoc khi chat.

### Pinecone Dense Search

Dense search dung:

```text
AITeamVN/Vietnamese_Embedding
```

De embed query, sau do query Pinecone theo cosine similarity.

### RRF

BM25 va Pinecone co thang diem khac nhau, nen backend dung Reciprocal Rank Fusion:

```text
score(d) = sum(1 / (k + rank_i(d)))
```

Mac dinh:

```text
RETRIEVAL_RRF_K=60
```

### Reranker

Sau RRF, backend rerank cac candidate bang:

```text
BAAI/bge-reranker-v2-m3
```

Reranker cham hon vector search vi no cham diem tung cap:

```text
(query, chunk_text)
```

De giam latency, chi nen rerank mot so candidate nho:

```text
RETRIEVAL_RERANK_TOP_N=8
```

Neu can nhanh hon co the giam:

```text
RETRIEVAL_RERANK_TOP_N=4
```

hoac tam tat:

```text
RERANKER_ENABLED=false
```

## 6. Context Packing

Sau khi co top chunks da rerank, backend goi:

```text
ContextPackingService.pack
```

Context dua vao Gemini khong phai toan bo thu tuc, ma la cac chunk nguon:

```text
[C1]
Thu tuc: ...
Ma thu tuc: ...
Muc: ...
Nguon: ...
Noi dung:
...

[C2]
...
```

Thu tu context dung chien luoc dat thong tin quan trong o dau va cuoi:

```text
rank 1 -> dau context
rank 2 -> cuoi context
rank 3 -> sau rank 1
rank 4 -> truoc rank 2
```

Muc tieu la giam rui ro model bo sot thong tin nam giua context.

## 7. Sinh Cau Tra Loi

Backend goi Gemini chat model voi prompt gom:

- `user_type`.
- Cau hoi moi.
- Query retrieval da dung.
- Route: `new_topic` hoac `follow_up`.
- Chat history ngan.
- Context chunks `[C1]`, `[C2]`, ...

Yeu cau voi model:

- Chi tra loi dua tren context.
- Khong bia them.
- Khong tom tat toan bo thu tuc neu nguoi dung chi hoi mot muc.
- Neu thieu thong tin, noi ro du lieu hien co chua thay.
- Khi dung thong tin, dan citation `[C1]`, `[C2]`.
- Co the giu markdown table trong cau tra loi neu context co bang.

Response chat gom:

```json
{
  "session_id": "...",
  "answer": "...",
  "procedures": [],
  "sources": [],
  "inference_seconds": 12.34,
  "expires_at": null
}
```

`sources` la phan UI hien thi thanh chunk nguon.

## 8. Cau Hoi Tiep Theo

Cau hoi tiep theo khong chi dung context cu.

Frontend goi:

```text
POST /api/chat/sessions/{session_id}/messages
```

hoac voi local chat:

```text
POST /api/chat/local/messages
```

Backend xu ly:

```text
chat history ngan + cau hoi moi
  -> ChatRoutingService
  -> phan loai follow_up hoac new_topic
  -> neu follow_up: rewrite query co ngu canh
  -> neu new_topic: dung cau hoi moi
  -> retrieve lai BM25 + Pinecone
  -> RRF + rerank
  -> context packing moi
  -> Gemini tra loi
```

Vi moi turn deu retrieve lai, he thong khong bi ket vao context cu. Neu nguoi dung chuyen chu de, AI co the tim thu tuc moi.

## 9. Luu Chat

Neu user dang nhap Google, backend luu vao Supabase:

```text
chat_sessions
chat_messages
```

Trong `chat_sessions`:

- `user_id`
- `user_type`
- `initial_question`
- `procedure_context`
- `source_context`
- `created_at`
- `updated_at`

Trong `chat_messages.metadata`:

- `procedures`
- `sources`
- `route`
- `query`
- `inference_seconds`

Neu user khong dang nhap:

- Chat van chay.
- Session co dang `local:...`.
- Lich su khong luu vao database.
- Frontend giu context local tam thoi.

## 10. UI Hien Tai

Tab "Hoi AI" hien thi:

- Khung chat o giua.
- Cau tra loi co citation `[C1]`, `[C2]`.
- Phan "Nguon da dung" ben duoi cau tra loi.
- Panel ben phai hien thi "Chunk nguon gan nhat".
- Khong hien danh sach thu tuc rieng o phia tren panel nua.

Panel phai hien:

```text
8 chunk nguon

[C1] Thanh phan ho so
Ten thu tuc...
Preview chunk...
Nguon

[C2] Trinh tu thuc hien
...
```

Neu cau tra loi co markdown table, frontend render thanh bang.

## 11. Tim Them Nguon Trong UI

O panel phai, nguoi dung co the tim thu tuc/chunk de them vao context.

Luong:

```text
keyword
  -> POST /api/search/vector
  -> HybridRetrievalService.search
  -> tra danh sach thu tuc suy ra tu chunks
  -> nguoi dung bam Them
  -> backend lay summary thu tuc
  -> them vao context hien tai
```

Luu y: cau hoi tiep theo van retrieve lai tu BM25 + Pinecone, nen context manual khong phai gioi han cung.

## 12. Thoi Gian Suy Luan Va Log

Backend tra:

```json
{
  "inference_seconds": 12.34
}
```

Frontend hien:

```text
Thoi gian suy luan: 12,3 giay
```

Backend cung log retrieval timing:

```text
[bm25] indexed 19414 chunks from cache in 2.31s
[retrieval] bm25=2.40s dense=1.20s hydrate=0.50s rerank=3.10s total=7.20s candidates=54
```

Neu thay:

```text
[bm25] indexed ... from live in 300s
```

nghia la chua co BM25 cache hoac cache khong hop le. Can chay:

```powershell
python -m app.cli bm25-build-cache
```

roi restart backend.

## 13. Evaluation

Evaluation retrieval chay thu cong bang CLI.

Dataset nam trong:

```text
retrieval_eval_questions
```

Ket qua luu vao:

```text
retrieval_eval_results
```

Lenh:

```powershell
python -m app.cli eval-retrieval --run-name rag-v1 --k 8 --save
```

Metrics:

- Precision@K
- Recall@K
- MRR
- NDCG@K

Ground truth ban dau du kien:

- AI sinh 100 cau hoi.
- Human review lai `relevant_chunk_ids` va `relevant_procedure_ids`.

## 14. Cac Thanh Phan Code Chinh

Backend:

```text
apps/api/app/services/chat_service.py
apps/api/app/services/chat_routing_service.py
apps/api/app/services/hybrid_retrieval_service.py
apps/api/app/services/bm25_service.py
apps/api/app/services/pinecone_vector_service.py
apps/api/app/services/huggingface_embedding_service.py
apps/api/app/services/rerank_service.py
apps/api/app/services/context_packing_service.py
apps/api/app/services/document_extraction_service.py
apps/api/app/services/chunking_service.py
apps/api/app/services/rag_build_service.py
apps/api/app/services/supabase_repo.py
apps/api/app/api.py
apps/api/app/cli.py
```

Frontend:

```text
apps/web/src/App.tsx
apps/web/src/api.ts
```

Database/migrations:

```text
supabase/migrations/0004_rag_pipeline.sql
```

Runbook:

```text
RAG_RUNBOOK.md
```

## 15. Tom Tat Luong Tong Quat

```text
User question
  -> route/rewrite neu can
  -> BM25 search tu local cache
  -> dense search tu Pinecone
  -> RRF fusion
  -> lay full chunks tu Supabase
  -> bge rerank
  -> pack chunks thanh context [C1]...[C8]
  -> Gemini generate answer
  -> frontend hien answer + chunk sources
```

Ket hop database:

```text
Supabase
  giu du lieu goc, markdown, chunks, chat, evaluation

Pinecone
  giu vector embedding cua chunks de semantic search

BM25 cache file
  giu lexical index da tokenize de search nhanh luc runtime
```

