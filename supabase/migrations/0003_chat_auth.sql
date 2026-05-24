alter table public.chat_sessions
add column if not exists user_id uuid references auth.users(id) on delete cascade;

create index if not exists chat_sessions_user_id_idx
on public.chat_sessions (user_id, updated_at desc);

drop policy if exists "Users can read own chat sessions" on public.chat_sessions;
create policy "Users can read own chat sessions"
on public.chat_sessions for select
using (auth.uid() = user_id);

drop policy if exists "Users can read own chat messages" on public.chat_messages;
create policy "Users can read own chat messages"
on public.chat_messages for select
using (
  exists (
    select 1 from public.chat_sessions cs
    where cs.id = chat_messages.session_id
      and cs.user_id = auth.uid()
  )
);
