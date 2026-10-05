-- Transakcje zakupu (dokupienia) per pozycja. portfolio_positions pozostaje
-- agregatem (quantity = suma, avg_buy_price = średnia ważona) przeliczanym w API.
create table public.portfolio_transactions (
  id uuid primary key default gen_random_uuid(),
  position_id uuid not null references public.portfolio_positions (id) on delete cascade,
  user_id uuid not null references auth.users (id) on delete cascade,
  quantity numeric not null check (quantity > 0),
  price numeric check (price > 0),          -- nullable: backfill starych pozycji bez ceny
  purchased_at date not null default current_date,
  created_at timestamptz not null default now()
);
create index portfolio_transactions_position_idx
  on public.portfolio_transactions (position_id);
create index portfolio_transactions_user_idx
  on public.portfolio_transactions (user_id);

grant select, insert, update, delete on public.portfolio_transactions to authenticated;

alter table public.portfolio_transactions enable row level security;

create policy "select own" on public.portfolio_transactions
  for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "insert own" on public.portfolio_transactions
  for insert to authenticated
  with check ((select auth.uid()) = user_id);
create policy "update own" on public.portfolio_transactions
  for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
create policy "delete own" on public.portfolio_transactions
  for delete to authenticated
  using ((select auth.uid()) = user_id);

-- Backfill: każda istniejąca pozycja dostaje jedną transakcję startową.
insert into public.portfolio_transactions
  (position_id, user_id, quantity, price, purchased_at, created_at)
select id, user_id, quantity, avg_buy_price, created_at::date, created_at
from public.portfolio_positions;
