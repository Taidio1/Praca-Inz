-- Silnik informacyjny: ingest, relevance, synteza, ewaluacja (spec 2026-10-05 §8).
-- Cały schemat w jednej migracji, żeby etapy 2-5 nie wymagały kolejnych.

create extension if not exists vector;

-- ===== source_items: deduplikacja, embedding, stan relevance =====
alter table public.source_items drop constraint source_items_source_check;
alter table public.source_items
  add constraint source_items_source_check
  check (source in ('gdelt', 'rss', 'gemini', 'finnhub'));

alter table public.source_items
  add column title_hash text,
  add column duplicate_of uuid references public.source_items (id) on delete set null,
  add column embedding vector(384),
  add column embedding_model text,
  add column best_score numeric check (best_score >= 0 and best_score <= 1),
  add column relevance_done_at timestamptz;

create index source_items_relevance_pending_idx
  on public.source_items (fetched_at) where relevance_done_at is null;
create index source_items_title_hash_idx on public.source_items (title_hash, fetched_at);
create index source_items_fetched_idx on public.source_items (fetched_at desc);

-- ===== item_relevance: składowe wyniku =====
alter table public.item_relevance drop constraint item_relevance_method_check;
alter table public.item_relevance
  add constraint item_relevance_method_check
  check (method in ('ticker_match', 'embedding', 'combined', 'llm_judge'));
alter table public.item_relevance
  add column match_score numeric,
  add column embedding_score numeric;

-- ===== asset_profiles: profil aktywa dla filtra trafności =====
create table public.asset_profiles (
  asset_id uuid primary key references public.assets (id) on delete cascade,
  names text[] not null default '{}',
  ticker_patterns text[] not null default '{}',
  negative_terms text[] not null default '{}',
  keywords text[] not null default '{}',
  market text not null check (market in ('crypto', 'us', 'gpw', 'eu_etf')),
  profile_text text not null,
  embedding vector(384),
  embedding_model text,
  generated_by text not null check (generated_by in ('llm', 'manual')),
  llm_run_id uuid references public.llm_runs (id) on delete set null,
  updated_at timestamptz not null default now()
);

-- ===== source_state: stan pobierania per klucz źródła =====
create table public.source_state (
  source_key text primary key,
  last_fetched_at timestamptz,
  etag text,
  last_modified text,
  consecutive_failures integer not null default 0,
  last_error text,
  updated_at timestamptz not null default now()
);

-- ===== engine_cycles: log cykli workera =====
create table public.engine_cycles (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  stats jsonb not null default '{}'::jsonb,
  errors jsonb not null default '{}'::jsonb
);
create index engine_cycles_started_idx on public.engine_cycles (started_at desc);

-- ===== llm_runs: cel, status, cache =====
alter table public.llm_runs
  add column purpose text not null default 'synthesis'
    check (purpose in ('synthesis', 'profile', 'judge')),
  add column status text not null default 'ok'
    check (status in ('ok', 'invalid', 'error')),
  add column error text,
  add column cache_read_tokens integer not null default 0;
alter table public.llm_runs alter column asset_id drop not null;

-- ===== insights: wyzwalacz syntezy =====
alter table public.insights
  add column trigger text check (trigger in ('important', 'batch', 'daily'));

-- ===== relevance_labels: etykiety ewaluacyjne (per użytkownik) =====
create table public.relevance_labels (
  user_id uuid not null references auth.users (id) on delete cascade,
  item_id uuid not null references public.source_items (id) on delete cascade,
  asset_id uuid not null references public.assets (id) on delete cascade,
  relevant boolean not null,
  created_at timestamptz not null default now(),
  primary key (user_id, item_id, asset_id)
);

-- ===== Grants + RLS =====
grant select on public.asset_profiles, public.source_state, public.engine_cycles to authenticated;
grant select, insert, update, delete on public.relevance_labels to authenticated;

alter table public.asset_profiles enable row level security;
alter table public.source_state enable row level security;
alter table public.engine_cycles enable row level security;
alter table public.relevance_labels enable row level security;

create policy "authenticated read" on public.asset_profiles
  for select to authenticated using (true);
create policy "authenticated read" on public.source_state
  for select to authenticated using (true);
create policy "authenticated read" on public.engine_cycles
  for select to authenticated using (true);

create policy "select own" on public.relevance_labels
  for select to authenticated using ((select auth.uid()) = user_id);
create policy "insert own" on public.relevance_labels
  for insert to authenticated with check ((select auth.uid()) = user_id);
create policy "update own" on public.relevance_labels
  for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "delete own" on public.relevance_labels
  for delete to authenticated using ((select auth.uid()) = user_id);
