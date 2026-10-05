-- ===== Grupa 1: katalog i dane rynkowe (globalne; pisze silnik przez service_role) =====

create table public.assets (
  id uuid primary key default gen_random_uuid(),
  ticker text not null,
  name text not null,
  asset_type text not null check (asset_type in ('crypto', 'stock', 'etf')),
  aliases text[] not null default '{}',
  created_at timestamptz not null default now(),
  unique (ticker, asset_type)
);

create table public.market_snapshots (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets (id) on delete cascade,
  price numeric,
  change_24h numeric,
  indicators jsonb,
  funding jsonb,
  captured_at timestamptz not null default now()
);
create index market_snapshots_asset_time_idx
  on public.market_snapshots (asset_id, captured_at desc);

-- ===== Grupa 2: pipeline informacyjny i audyt (globalne; pisze silnik) =====

create table public.source_items (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source in ('gdelt', 'rss', 'gemini')),
  url text not null,
  title text not null,
  snippet text,
  published_at timestamptz,
  fetched_at timestamptz not null default now(),
  raw jsonb,
  unique (source, url)
);

create table public.item_relevance (
  item_id uuid not null references public.source_items (id) on delete cascade,
  asset_id uuid not null references public.assets (id) on delete cascade,
  score numeric not null check (score >= 0 and score <= 1),
  method text not null check (method in ('ticker_match', 'embedding')),
  reason text,
  created_at timestamptz not null default now(),
  primary key (item_id, asset_id)
);
create index item_relevance_asset_score_idx
  on public.item_relevance (asset_id, score desc);

create table public.llm_runs (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets (id) on delete cascade,
  provider text not null,
  model text not null,
  prompt text not null,
  response text not null,
  tokens_in integer not null default 0,
  tokens_out integer not null default 0,
  latency_ms integer not null default 0,
  cost_usd numeric not null default 0,
  created_at timestamptz not null default now()
);

create table public.insights (
  id uuid primary key default gen_random_uuid(),
  asset_id uuid not null references public.assets (id) on delete cascade,
  llm_run_id uuid not null references public.llm_runs (id) on delete restrict,
  title text not null,
  summary text not null,
  sentiment_score numeric not null check (sentiment_score >= -1 and sentiment_score <= 1),
  sentiment_label text not null,
  price_context text,
  created_at timestamptz not null default now()
);
create index insights_asset_time_idx on public.insights (asset_id, created_at desc);

create table public.insight_items (
  insight_id uuid not null references public.insights (id) on delete cascade,
  item_id uuid not null references public.source_items (id) on delete cascade,
  relevance numeric not null,
  primary key (insight_id, item_id)
);

-- ===== Grupa 3: dane użytkownika (per-user; CRUD przez API) =====

create table public.portfolio_positions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  asset_id uuid not null references public.assets (id) on delete cascade,
  quantity numeric not null check (quantity > 0),
  created_at timestamptz not null default now(),
  unique (user_id, asset_id)
);
create index portfolio_positions_user_idx on public.portfolio_positions (user_id);

create table public.user_settings (
  user_id uuid primary key references auth.users (id) on delete cascade,
  relevance_threshold numeric not null default 0.5
    check (relevance_threshold >= 0 and relevance_threshold <= 1),
  notifications jsonb not null default '{}'::jsonb
);

-- ===== Grants: dostęp ról Data API (RLS poniżej zawęża wiersze) =====

grant select on
  public.assets,
  public.market_snapshots,
  public.source_items,
  public.item_relevance,
  public.llm_runs,
  public.insights,
  public.insight_items
to authenticated;

grant select, insert, update, delete on public.portfolio_positions to authenticated;
grant select, insert, update on public.user_settings to authenticated;

-- ===== RLS: włączone na każdej tabeli =====

alter table public.assets enable row level security;
alter table public.market_snapshots enable row level security;
alter table public.source_items enable row level security;
alter table public.item_relevance enable row level security;
alter table public.llm_runs enable row level security;
alter table public.insights enable row level security;
alter table public.insight_items enable row level security;
alter table public.portfolio_positions enable row level security;
alter table public.user_settings enable row level security;

-- Globalne: odczyt dla zalogowanych; zapis wyłącznie service_role (brak polityk zapisu)

create policy "authenticated read" on public.assets
  for select to authenticated using (true);
create policy "authenticated read" on public.market_snapshots
  for select to authenticated using (true);
create policy "authenticated read" on public.source_items
  for select to authenticated using (true);
create policy "authenticated read" on public.item_relevance
  for select to authenticated using (true);
create policy "authenticated read" on public.llm_runs
  for select to authenticated using (true);
create policy "authenticated read" on public.insights
  for select to authenticated using (true);
create policy "authenticated read" on public.insight_items
  for select to authenticated using (true);

-- Per-user: polityki własnościowe

create policy "select own" on public.portfolio_positions
  for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "insert own" on public.portfolio_positions
  for insert to authenticated
  with check ((select auth.uid()) = user_id);
create policy "update own" on public.portfolio_positions
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
create policy "delete own" on public.portfolio_positions
  for delete to authenticated
  using ((select auth.uid()) = user_id);

create policy "select own" on public.user_settings
  for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "insert own" on public.user_settings
  for insert to authenticated
  with check ((select auth.uid()) = user_id);
create policy "update own" on public.user_settings
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
