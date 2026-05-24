create extension if not exists vector with schema extensions;

create table if not exists public.procedure_embeddings (
  id uuid primary key default gen_random_uuid(),
  procedure_id uuid not null references public.procedures(id) on delete cascade,
  procedure_code text not null,
  procedure_group text not null check (procedure_group in ('administrative', 'interlinked')),
  name text not null,
  field_name text,
  target_audience text,
  source_url text not null,
  embedding_model text not null,
  embedding_dim integer not null default 768,
  embedding vector(768) not null,
  content_hash text not null,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (procedure_code, procedure_group)
);

create index if not exists procedure_embeddings_group_idx
on public.procedure_embeddings (procedure_group);

create index if not exists procedure_embeddings_active_idx
on public.procedure_embeddings (is_active);

create index if not exists procedure_embeddings_embedding_hnsw_idx
on public.procedure_embeddings
using hnsw (embedding vector_cosine_ops);

drop trigger if exists procedure_embeddings_set_updated_at on public.procedure_embeddings;
create trigger procedure_embeddings_set_updated_at
before update on public.procedure_embeddings
for each row execute function public.set_updated_at();

alter table public.procedure_embeddings enable row level security;

create or replace function public.match_procedure_embeddings(
  query_embedding vector(768),
  match_count int default 9,
  filter_group text default null,
  filter_target_audience text default null
)
returns table (
  procedure_id uuid,
  procedure_code text,
  procedure_group text,
  name text,
  field_name text,
  target_audience text,
  source_url text,
  similarity double precision
)
language sql stable
as $$
  select
    pe.procedure_id,
    pe.procedure_code,
    pe.procedure_group,
    pe.name,
    pe.field_name,
    pe.target_audience,
    pe.source_url,
    1 - (pe.embedding <=> query_embedding) as similarity
  from public.procedure_embeddings pe
  where pe.is_active = true
    and (filter_group is null or pe.procedure_group = filter_group)
    and (
      filter_target_audience is null
      or pe.target_audience is null
      or pe.target_audience ilike '%' || filter_target_audience || '%'
    )
  order by pe.embedding <=> query_embedding
  limit match_count;
$$;
