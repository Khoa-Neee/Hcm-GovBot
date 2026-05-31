# RAG_REDESIGN_PLAN.md

Tai lieu nay mo ta nhung thay doi du kien cho he thong HCM GovBot theo huong RAG moi. Muc tieu cua file nay la de duyet thiet ke truoc khi code.

## 1. Hien Trang

He thong hien tai dang co pipeline:

```text
DVCQG crawler
  -> Supabase PostgreSQL bang procedures
  -> Gemini embedding
  -> Supabase pgvector bang procedure_embeddings
  -> vector search
  -> Gemini tom tat toi da 3 thu tuc
  -> tra loi chat
```

Gioi han hien tai:

- Crawler chu yeu lay text/JSON tu trang thu tuc, chua co buoc nhan dien bang phuc tap va chuan hoa bang thanh markdown.
- Embedding dang tao tren metadata thu tuc, chua chunk noi dung chi tiet theo cau truc parent-child.
- Retrieval chu yeu la vector search, chua co hybrid BM25 + embedding + RRF.
- Chua co reranker rieng.
- Context packing dang dua toi da 3 ban tom tat thu tuc vao prompt, chua co chien luoc sap xep chunk theo vi tri dau/cuoi context.
- Chua co bo danh gia retrieval/RAG chinh thuc bang Precision@K, Recall@K, MRR, NDCG hoac RAGAS.

## 2. Muc Tieu Thay Doi

Can nang cap pipeline RAG thanh:

```text
Crawl/detail extraction
  -> detect table
  -> HTML table extraction + python textract fallback
  -> markdown normalization
  -> parent-child chunking
  -> Vietnamese embedding model
  -> Pinecone vector database
  -> BM25 retrieval + dense retrieval
  -> RRF fusion
  -> bge-reranker
  -> context packing dau/cuoi
  -> answer generation
  -> evaluation
```

Ten "Pipecone" trong yeu cau duoc chot la "Pinecone".

## 2.1. Cac Quyet Dinh Da Chot

- Chi dung thu vien Python `textract`, khong dung Amazon Textract.
- Nguon can xu ly chi la HTML, khong OCR PDF/file dinh kem trong phase nay.
- Van can luu raw/extracted payload phuc vu debug neu co the.
- Cac loai bang/noi dung deu quan trong ngang nhau, khong uu tien rieng ho so/phi/trinh tu/can cu.
- Child chunk gioi han 512 tokens, overlap 50 tokens.
- Khong gioi han cung tong context theo so thu tuc; context tuy vao cau hoi va token budget cua model.
- Bo gioi han toi da 3 thu tuc trong UI/chat context.
- Pinecone index da duoc tao, dung cosine similarity, serverless.
- Co the chia namespace `dev` va `prod`.
- Khong can giu Supabase pgvector lam fallback; co the bo pgvector khoi retrieval chinh.
- BM25 dung in-memory.
- Tach tu tieng Viet cho BM25 bang `underthesea`.
- Query rewrite can dung khi cau hoi khong ro rang.
- Khong filter theo doi tuong ca nhan/doanh nghiep truoc retrieval.
- Reranker dung local model `BAAI/bge-reranker-v2-m3`.
- Latency reranker cho phep them toi da 1-2 giay moi cau hoi.
- Frontend can hien thi chunk nguon/citation.
- Van giu danh sach thu tuc trong UI, nhung khong gioi han 3 thu tuc.
- Neu cau tra loi co bang markdown thi frontend nen render thanh bang.
- Evaluation ground truth: AI sinh truoc, human review sau.
- Benchmark ban dau: 100 cau.
- Khong can chia bo test theo nhom cau hoi trong phase dau.
- Evaluation chay thu cong bang CLI, khong can CI.

## 3. Crawl Va Xu Ly Bang

### Can sua

- Bo sung lop extraction moi sau khi crawl detail.
- Phat hien cac vung du lieu dang bang trong noi dung thu tuc, dac biet:
  - thanh phan ho so;
  - cach thuc thuc hien;
  - phi/le phi;
  - trinh tu thuc hien;
  - can cu phap ly;
  - file bieu mau neu co bang dinh kem.
- Neu nguon la HTML table thi parse truc tiep tu HTML bang BeautifulSoup truoc.
- Thu vien Python `textract` chi dung nhu fallback extraction neu can doc noi dung dang file/text ma thu vien parse HTML khong xu ly duoc.
- Khong xu ly Amazon Textract, khong OCR PDF/scan/anh trong phase nay.
- Chuan hoa ket qua table thanh markdown table de dua vao chunk va prompt.
- Luu noi dung da chuan hoa vao database, tach rieng voi raw data.

### De xuat schema moi

Them bang hoac cot:

```text
procedure_documents
  id
  procedure_id
  source_type          -- html
  source_url
  normalized_markdown
  extraction_method    -- html_parser, python_textract, fallback_text
  raw_extracted_payload
  extraction_metadata
  content_hash
  created_at
  updated_at
```

### Da chot

- Dung thu vien Python `textract`, khong dung AWS/Amazon Textract.
- Chi xu ly HTML.
- Bo qua cau hinh AWS.
- Luu raw/extracted payload neu co the de debug.
- Tat ca bang/noi dung deu ngang uu tien.

## 4. Chunking Parent-Child

### Can sua

- Bo cach embedding 1 vector cho 1 thu tuc.
- Tao parent document theo tung thu tuc.
- Tao child chunks tu noi dung markdown cua thu tuc.
- Retrieval tra ve child chunks, sau do lay parent metadata/context can thiet de generate.

### De xuat cau truc

Parent:

```text
procedure_id
procedure_code
name
procedure_group
field_name
target_audience
implementation_agency
source_url
full_markdown
content_hash
```

Child chunk:

```text
chunk_id
parent_id/procedure_id
chunk_index
section_name
chunk_text
chunk_markdown
token_count
content_hash
metadata
```

### Chien luoc chunking

- Chunk theo section truoc: ho so, trinh tu, phi/le phi, thoi han, co quan, yeu cau, can cu phap ly.
- Giu markdown table nguyen khoi neu bang khong qua dai.
- Neu section qua dai thi split tiep theo token voi kich thuoc 512 tokens va overlap 50 tokens.
- Child chunk phai co header ngan de khong mat ngu canh:

```text
Thu tuc: ...
Ma thu tuc: ...
Muc: Thanh phan ho so

<noi dung chunk>
```

### Da chot

- Child chunk: 512 tokens.
- Overlap: 50 tokens.
- Khong gioi han context theo toi da 3 thu tuc.
- Context final tuy theo cau hoi va token budget cua model, nhung prompt khong duoc tra loi tran lan/toan bo thu tuc neu nguoi dung chi hoi mot phan.

## 5. Embedding Model

### Can sua

- Thay Gemini embedding bang model Hugging Face:

```text
AITeamVN/Vietnamese_Embedding
```

- Tao service embedding moi, chay model Hugging Face local.
- Embedding cho child chunks, khong chi metadata thu tuc.
- Luu `embedding_model`, `embedding_dim`, `content_hash` de biet khi nao can re-embed.

### Da chot va con can kiem tra ky thuat

- Chay embedding local.
- Van can code tu dong xac nhan embedding dimension cua `AITeamVN/Vietnamese_Embedding` truoc khi upsert vao Pinecone.
- Neu may khong co GPU, pipeline van phai chay CPU duoc nhung co the cham; can batch embedding de giam thoi gian sync.

## 6. Vector Database: Pinecone

### Can sua

- Thay Supabase pgvector cho retrieval chinh bang Pinecone.
- Supabase van nen giu vai tro database goc cho:
  - procedures;
  - normalized documents;
  - chunks metadata;
  - chat sessions/messages;
  - evaluation datasets/results.
- Pinecone luu vector child chunks va metadata can filter.
- Supabase pgvector khong can giu lam fallback; sau khi Pinecone pipeline on dinh co the bo code/bang lien quan pgvector.

### De xuat metadata trong Pinecone

```json
{
  "chunk_id": "...",
  "procedure_id": "...",
  "procedure_code": "...",
  "procedure_group": "administrative",
  "name": "...",
  "field_name": "...",
  "target_audience": "...",
  "implementation_agency": "...",
  "section_name": "...",
  "source_url": "...",
  "content_hash": "..."
}
```

### Da chot

- Pinecone index da tao san.
- Metric: cosine similarity.
- Loai index: serverless.
- Namespace: dung `dev` va `prod`.
- Khong giu pgvector lam fallback.

## 7. Retrieval: BM25 + Dense + RRF

### Can sua

- Tao retrieval service moi gom:
  - BM25 lexical search;
  - dense embedding search tren Pinecone;
  - fusion bang Reciprocal Rank Fusion.
- Bo hoac giam vai tro buoc "LLM doan ten thu tuc" hien tai. Thay bang query rewrite khi cau hoi khong ro rang; retrieval chinh dua tren cau hoi goc va/hoac rewritten query.
- Khong filter theo doi tuong ca nhan/doanh nghiep truoc retrieval.

### De xuat luong

```text
question
  -> query rewrite neu cau hoi khong ro
  -> BM25 top N bang underthesea tokenizer
  -> Pinecone dense top N
  -> RRF merge
  -> bge-reranker top K
  -> context packing
```

RRF score:

```text
score(d) = sum(1 / (k + rank_i(d)))
```

De xuat ban dau:

```text
BM25 top_n = 30
Dense top_n = 30
RRF k = 60
Rerank input = 30
Final chunks = 6-10
```

### BM25 storage/index da chot

- Dung in-memory BM25 build tu chunks khi backend start.
- Dung `underthesea` de word tokenize tieng Viet truoc khi index/search.
- Chua dung Elasticsearch/OpenSearch trong phase nay.

### Query rewrite da chot

- Neu cau hoi ro rang: retrieve truc tiep.
- Neu cau hoi ngan/mo ho/khong du ngu canh: rewrite dua tren chat history ngan va cau hoi moi.
- Query rewrite co the dung Gemini chat model hien tai.

## 8. Rerank: bge-reranker

### Can sua

- Them rerank service sau RRF.
- Dung bge-reranker de cham diem cap:

```text
(question, chunk_text)
```

- Sap xep lai ung vien va cat top K truoc khi dua vao context.

### Da chot

- Model: `BAAI/bge-reranker-v2-m3`.
- Chay local.
- Latency them toi da 1-2 giay moi cau hoi. Neu vuot nguong, can giam `RERANKER_TOP_N` hoac batch size.

## 9. Dua Data Vao Context

### Can sua

- Chuyen tu context "toi da 3 tom tat thu tuc" sang context gom cac chunk da rerank.
- Van giu danh sach thu tuc trong UI/chat context, nhung danh sach nay khong con gioi han 3 thu tuc va duoc suy ra tu cac chunk/source dang dung.
- Bo sung chien luoc sap xep chunk trong prompt theo nhan xet:
  - thong tin quan trong nhat nen nam dau va cuoi context;
  - thong tin o giua de bi model bo sot hon.

### De xuat packing

Voi danh sach chunk da rerank:

```text
rank 1 -> dau context
rank 2 -> cuoi context
rank 3 -> sau rank 1
rank 4 -> truoc rank 2
rank 5+ -> giua neu con budget
```

Context nen co citation marker:

```text
[C1]
Thu tuc: ...
Ma thu tuc: ...
Muc: ...
Nguon: ...
Noi dung:
...
```

Prompt answer yeu cau:

- Chi tra loi tu context.
- Neu thieu thong tin, noi ro chua co trong du lieu.
- Neu dung thong tin nao, dan citation `[C1]`, `[C2]`.
- Uu tien noi dung co rank cao.

### Da chot

- UI can hien thi chunk nguon/citation.
- Giu danh sach thu tuc trong UI.
- Neu answer/context co markdown table, frontend nen render thanh bang.

## 9.1. Xu Ly Cau Hoi Tiep Theo Trong Chat

Khong dung co dinh context cu cho moi cau hoi tiep theo. Moi tin nhan moi can di qua buoc phan loai va retrieve lai khi can.

Luong moi:

```text
chat history ngan + cau hoi moi
  -> xac dinh follow-up hay topic moi
  -> neu follow-up: rewrite query co ngu canh tu history/context truoc
  -> neu topic moi: retrieve nhu cau hoi moi
  -> BM25 + dense retrieval
  -> RRF
  -> rerank
  -> context packing moi
  -> sinh cau tra loi bang context moi + history ngan
```

Quy tac:

- Follow-up la cau hoi phu thuoc vao ngu canh truoc, vi du "phi bao nhieu", "can giay to gi", "nop o dau".
- Topic moi la cau hoi nhac sang nhu cau/thu tuc khac, vi du dang hoi ho khau nhung chuyen sang giay phep kinh doanh.
- Ke ca follow-up cung retrieve lai bang rewritten query de tranh chi dung context cu va bo sot thong tin.
- History dua vao generation chi nen la ban tom tat ngan cua vai luot gan nhat, khong dua toan bo lich su neu dai.
- Context moi thay the/bo sung context hien tai, dong thoi cap nhat danh sach thu tuc/chunk nguon tren UI.

## 10. Evaluation

### Can sua

- Them bo evaluation offline cho retrieval va RAG.
- Luu bo cau hoi benchmark va ground truth.

### Retrieval metrics

Can tinh:

```text
Precision@K
Recall@K
MRR
NDCG@K
```

Can dataset dang:

```json
{
  "question": "...",
  "relevant_procedure_ids": ["..."],
  "relevant_chunk_ids": ["..."],
  "expected_sections": ["required_documents", "fees"]
}
```

### RAGAS

Danh gia cac chi so RAGAS co the gom:

- faithfulness;
- answer relevancy;
- context precision;
- context recall;
- answer correctness neu co reference answer.

### Da chot

- Ground truth sinh ban dau bang AI, sau do human review.
- Benchmark ban dau: 100 cau.
- Khong can chia bo test theo nhom cau hoi trong phase dau.
- Evaluation chay thu cong bang CLI.

## 11. Anh Huong Den Code Hien Tai

Backend can them/sua:

```text
apps/api/app/config.py
apps/api/app/crawler.py
apps/api/app/sync.py
apps/api/app/services/supabase_repo.py
apps/api/app/services/supabase_vector_service.py     -- co the thay/bo
apps/api/app/services/chat_service.py
apps/api/app/cli.py
apps/api/app/api.py
```

Backend can them module moi:

```text
apps/api/app/services/document_extraction_service.py
apps/api/app/services/chunking_service.py
apps/api/app/services/huggingface_embedding_service.py
apps/api/app/services/pinecone_vector_service.py
apps/api/app/services/bm25_service.py
apps/api/app/services/hybrid_retrieval_service.py
apps/api/app/services/rerank_service.py
apps/api/app/services/context_packing_service.py
apps/api/app/services/chat_routing_service.py
apps/api/app/evaluation/
```

Database/migrations can them:

```text
procedure_documents
procedure_chunks
retrieval_eval_questions
retrieval_eval_results
rag_eval_results
```

Frontend co the can sua:

```text
apps/web/src/api.ts
apps/web/src/App.tsx
```

Neu API chat response them citations/sources, frontend can hien thi nguon theo chunk/citation.

## 12. Bien Moi Trong `.env`

Du kien them:

```text
# Extraction
PYTHON_TEXTRACT_ENABLED=true

# Hugging Face
EMBEDDING_PROVIDER=huggingface
HF_TOKEN=
HF_EMBEDDING_MODEL=AITeamVN/Vietnamese_Embedding
HF_EMBEDDING_DEVICE=cpu
HF_EMBEDDING_BATCH_SIZE=16

# Pinecone
PINECONE_API_KEY=
PINECONE_INDEX_NAME=hcm-govbot
PINECONE_NAMESPACE=dev
PINECONE_METRIC=cosine

# Retrieval
RETRIEVAL_BM25_TOP_N=30
RETRIEVAL_DENSE_TOP_N=30
RETRIEVAL_RRF_K=60
RETRIEVAL_RERANK_TOP_N=8
RETRIEVAL_FINAL_TOP_K=8

# Reranker
RERANKER_ENABLED=true
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RERANKER_DEVICE=cpu
RERANKER_MAX_LATENCY_SECONDS=2

# BM25
BM25_TOKENIZER=underthesea
BM25_CACHE_PATH=.rag_cache/bm25_cache.pkl

# Chat routing/rewrite
CHAT_RETRIEVE_EVERY_TURN=true
CHAT_REWRITE_WHEN_AMBIGUOUS=true
```

## 13. Ke Hoach Thuc Hien De Xuat

### Phase 1: Thiet ke va schema

- Ap dung cac quyet dinh da chot trong section 2.1.
- Them migration cho `procedure_documents` va `procedure_chunks`.
- Them config/env moi.

### Phase 2: Extraction va markdown

- Parse HTML table thanh markdown.
- Them adapter Python `textract` neu can fallback extraction.
- Luu normalized markdown.

### Phase 3: Parent-child chunking

- Tao chunking service.
- Tao CLI build chunks tu procedures/documents.
- Luu chunks vao Supabase.

### Phase 4: Embedding va Pinecone

- Them embedding service cho `AITeamVN/Vietnamese_Embedding`.
- Tao Pinecone index/upsert/search.
- Tao CLI sync chunks -> Pinecone.

### Phase 5: Hybrid retrieval

- Them BM25 index.
- Them dense search.
- Them RRF fusion.
- Sua chat service dung retrieval moi.
- Them chat routing: follow-up/topic moi, rewrite khi can, retrieve lai moi turn.

### Phase 6: Rerank va context packing

- Them bge-reranker.
- Them context packing dau/cuoi.
- Tra ve citations/sources/chunk nguon.
- Frontend render citation va markdown table.

### Phase 7: Evaluation

- Tao dataset mau.
- Them CLI evaluation retrieval metrics.
- Them RAGAS evaluation neu co reference/LLM evaluator.

## 14. Rui Ro Va Diem Can Can Nhac

- Python `textract` co the khong can thiet neu nguon chi HTML; uu tien HTML parser truoc.
- Model embedding/reranker local co the cham neu khong co GPU.
- Pinecone can dung dimension dung voi model embedding, neu sai phai tao lai index.
- Hybrid retrieval can tokenizer tieng Viet tot de BM25 co y nghia.
- Context packing can test bang evaluation vi chien luoc dau/cuoi co the tot hon tuy model va prompt.
- RAGAS can reference answer hoac LLM evaluator, chi phi co the tang.

## 15. Can Duyet Truoc Khi Code

Nhung diem can ban duyet lan cuoi:

1. Dong y bo Supabase pgvector khoi retrieval chinh va chuyen sang Pinecone hoan toan.
2. Dong y khong xu ly OCR/PDF/file dinh kem trong phase dau, chi HTML.
3. Dong y chat moi turn deu co buoc phan loai follow-up/topic moi va retrieve lai.
4. Dong y context khong gioi han 3 thu tuc, nhung phai bi rang buoc boi token budget cua model va muc tieu cau hoi.
5. Dong y them hien thi chunk nguon/citation va render markdown table tren frontend.
6. Dong y evaluation ban dau gom 100 cau sinh bang AI va human review, chay bang CLI thu cong.
