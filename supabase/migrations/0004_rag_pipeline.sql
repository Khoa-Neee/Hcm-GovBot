create table if not exists public.procedure_documents (
  id uuid primary key default gen_random_uuid(),
  procedure_id uuid not null references public.procedures(id) on delete cascade,
  source_type text not null default 'html',
  source_url text not null,
  normalized_markdown text not null,
  extraction_method text not null default 'html_parser',
  raw_extracted_payload jsonb not null default '{}'::jsonb,
  extraction_metadata jsonb not null default '{}'::jsonb,
  content_hash text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (procedure_id, source_type)
);

create index if not exists procedure_documents_procedure_idx
on public.procedure_documents (procedure_id);

create table if not exists public.procedure_chunks (
  id uuid primary key default gen_random_uuid(),
  chunk_id text not null unique,
  procedure_id uuid not null references public.procedures(id) on delete cascade,
  document_id uuid references public.procedure_documents(id) on delete cascade,
  procedure_code text not null,
  procedure_group text not null check (procedure_group in ('administrative', 'interlinked')),
  name text not null,
  field_name text,
  target_audience text,
  implementation_agency text,
  section_name text not null,
  chunk_index integer not null,
  chunk_text text not null,
  chunk_markdown text not null,
  token_count integer not null default 0,
  source_url text not null,
  content_hash text not null,
  metadata jsonb not null default '{}'::jsonb,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (procedure_id, chunk_index)
);

create index if not exists procedure_chunks_procedure_idx
on public.procedure_chunks (procedure_id);

create index if not exists procedure_chunks_active_idx
on public.procedure_chunks (is_active);

create index if not exists procedure_chunks_section_idx
on public.procedure_chunks (section_name);

create index if not exists procedure_chunks_content_hash_idx
on public.procedure_chunks (content_hash);

create table if not exists public.retrieval_eval_questions (
  id uuid primary key default gen_random_uuid(),
  question text not null,
  reference_answer text,
  relevant_procedure_ids uuid[] not null default '{}'::uuid[],
  relevant_chunk_ids text[] not null default '{}'::text[],
  expected_sections text[] not null default '{}'::text[],
  generated_by text not null default 'ai',
  reviewed boolean not null default false,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.retrieval_eval_results (
  id uuid primary key default gen_random_uuid(),
  eval_question_id uuid references public.retrieval_eval_questions(id) on delete cascade,
  question text not null,
  run_name text not null,
  k integer not null,
  precision_at_k double precision not null default 0,
  recall_at_k double precision not null default 0,
  mrr double precision not null default 0,
  ndcg_at_k double precision not null default 0,
  retrieved_chunk_ids text[] not null default '{}'::text[],
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.rag_eval_results (
  id uuid primary key default gen_random_uuid(),
  eval_question_id uuid references public.retrieval_eval_questions(id) on delete cascade,
  question text not null,
  answer text not null,
  run_name text not null,
  metrics jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.chat_sessions
add column if not exists source_context jsonb not null default '[]'::jsonb;

drop trigger if exists procedure_documents_set_updated_at on public.procedure_documents;
create trigger procedure_documents_set_updated_at
before update on public.procedure_documents
for each row execute function public.set_updated_at();

drop trigger if exists procedure_chunks_set_updated_at on public.procedure_chunks;
create trigger procedure_chunks_set_updated_at
before update on public.procedure_chunks
for each row execute function public.set_updated_at();

drop trigger if exists retrieval_eval_questions_set_updated_at on public.retrieval_eval_questions;
create trigger retrieval_eval_questions_set_updated_at
before update on public.retrieval_eval_questions
for each row execute function public.set_updated_at();

alter table public.procedure_documents enable row level security;
alter table public.procedure_chunks enable row level security;
alter table public.retrieval_eval_questions enable row level security;
alter table public.retrieval_eval_results enable row level security;
alter table public.rag_eval_results enable row level security;

drop policy if exists "Public can read active procedure documents" on public.procedure_documents;
create policy "Public can read active procedure documents"
on public.procedure_documents for select
using (
  exists (
    select 1 from public.procedures p
    where p.id = procedure_documents.procedure_id
      and p.is_active = true
  )
);

drop policy if exists "Public can read active procedure chunks" on public.procedure_chunks;
create policy "Public can read active procedure chunks"
on public.procedure_chunks for select
using (
  is_active = true
  and exists (
    select 1 from public.procedures p
    where p.id = procedure_chunks.procedure_id
      and p.is_active = true
  )
);
