create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create table if not exists public.procedures (
  id uuid primary key default gen_random_uuid(),
  source_id text not null,
  procedure_code text not null,
  procedure_group text not null check (procedure_group in ('administrative', 'interlinked')),
  name text not null,
  target_audience text,
  field_name text,
  published_agency text,
  implementation_agency text,
  implementation_level text,
  execution_methods jsonb not null default '[]'::jsonb,
  execution_steps text,
  required_documents text,
  processing_time text,
  fees text,
  requirements text,
  legal_basis text,
  attachments jsonb not null default '[]'::jsonb,
  related_procedures jsonb not null default '[]'::jsonb,
  source_url text not null,
  raw_summary jsonb not null default '{}'::jsonb,
  raw_detail jsonb not null default '{}'::jsonb,
  content_hash text not null,
  is_active boolean not null default true,
  last_seen_at timestamptz not null default now(),
  source_updated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (procedure_code, procedure_group)
);

create index if not exists procedures_group_idx on public.procedures (procedure_group);
create index if not exists procedures_active_idx on public.procedures (is_active);
create index if not exists procedures_field_idx on public.procedures (field_name);
create index if not exists procedures_agency_idx on public.procedures (implementation_agency);
create index if not exists procedures_last_seen_idx on public.procedures (last_seen_at desc);
create index if not exists procedures_name_trgm_idx on public.procedures using gin (name gin_trgm_ops);

create table if not exists public.procedure_attachments (
  id uuid primary key default gen_random_uuid(),
  procedure_id uuid not null references public.procedures(id) on delete cascade,
  title text,
  file_url text,
  file_type text,
  source_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.crawl_runs (
  id uuid primary key default gen_random_uuid(),
  source_name text not null,
  procedure_group text not null check (procedure_group in ('administrative', 'interlinked')),
  status text not null check (status in ('running', 'success', 'failed')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  total_seen integer not null default 0,
  inserted_count integer not null default 0,
  updated_count integer not null default 0,
  unchanged_count integer not null default 0,
  inactivated_count integer not null default 0,
  error_message text,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.procedure_versions (
  id uuid primary key default gen_random_uuid(),
  procedure_id uuid references public.procedures(id) on delete set null,
  procedure_code text not null,
  procedure_group text not null,
  content_hash text not null,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.vector_sync_logs (
  id uuid primary key default gen_random_uuid(),
  procedure_id uuid references public.procedures(id) on delete set null,
  procedure_code text not null,
  status text not null check (status in ('pending', 'success', 'failed')),
  error_message text,
  created_at timestamptz not null default now()
);

create table if not exists public.chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_type text check (user_type in ('individual', 'business')),
  initial_question text,
  procedure_context jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system')),
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists procedures_set_updated_at on public.procedures;
create trigger procedures_set_updated_at
before update on public.procedures
for each row execute function public.set_updated_at();

drop trigger if exists chat_sessions_set_updated_at on public.chat_sessions;
create trigger chat_sessions_set_updated_at
before update on public.chat_sessions
for each row execute function public.set_updated_at();

alter table public.procedures enable row level security;
alter table public.procedure_attachments enable row level security;
alter table public.crawl_runs enable row level security;
alter table public.procedure_versions enable row level security;
alter table public.vector_sync_logs enable row level security;
alter table public.chat_sessions enable row level security;
alter table public.chat_messages enable row level security;

create policy "Public can read active procedures"
on public.procedures for select
using (is_active = true);

create policy "Public can read procedure attachments"
on public.procedure_attachments for select
using (
  exists (
    select 1 from public.procedures p
    where p.id = procedure_attachments.procedure_id
      and p.is_active = true
  )
);
