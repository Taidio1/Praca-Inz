-- Obsługa wielu walut.
--  * assets.currency                — waluta notowania aktywa (z dostawcy danych)
--  * portfolio_transactions.currency — waluta, w której podano cenę transakcji
--  * portfolio_transactions.fx_rate  — kurs waluty transakcji → waluty notowania
--                                      z dnia purchased_at (fx_rate_date = dzień publikacji)
--  * user_settings.base_currency     — waluta bazowa podsumowań portfela
--  * fx_rates                        — cache kursów historycznych (NBP / EBC)
--
-- Istniejące dane: aktywa (krypto = pary USDT, akcje/ETF z USA) i transakcje były
-- w całości w USD, więc dostają currency = 'USD', a kurs USD→USD z dnia zakupu to
-- dokładnie 1. Kwoty nie są przeliczane — nic nie zmienia wartości.

-- ===== Aktywa =====
alter table public.assets add column currency text;
update public.assets set currency = 'USD' where currency is null;
alter table public.assets
  alter column currency set not null,
  add constraint assets_currency_format check (currency ~ '^[A-Z]{3}$');

-- ===== Transakcje =====
alter table public.portfolio_transactions
  add column currency text,
  add column fx_rate numeric,
  add column fx_rate_date date;
update public.portfolio_transactions
  set currency = 'USD', fx_rate = 1, fx_rate_date = purchased_at
  where currency is null;
alter table public.portfolio_transactions
  alter column currency set not null,
  alter column fx_rate set not null,
  alter column fx_rate_date set not null,
  add constraint portfolio_transactions_currency_format check (currency ~ '^[A-Z]{3}$'),
  add constraint portfolio_transactions_fx_rate_positive check (fx_rate > 0);

-- ===== Ustawienia =====
alter table public.user_settings
  add column base_currency text not null default 'PLN'
    check (base_currency in ('PLN', 'USD', 'EUR'));

-- ===== Kursy walut (globalne; pisze backend przez service_role) =====
-- Jeden wiersz na żądany dzień: rate_date = dzień, na który kurs obowiązuje,
-- effective_date = dzień publikacji (weekend/święto → ostatnia wcześniejsza tabela).
create table public.fx_rates (
  base text not null check (base ~ '^[A-Z]{3}$'),
  quote text not null check (quote ~ '^[A-Z]{3}$'),
  rate_date date not null,
  rate numeric not null check (rate > 0),
  effective_date date not null,
  source text not null check (source in ('nbp', 'frankfurter')),
  fetched_at timestamptz not null default now(),
  primary key (base, quote, rate_date),
  check (effective_date <= rate_date)
);

grant select on public.fx_rates to authenticated;
alter table public.fx_rates enable row level security;

-- Globalne: odczyt dla zalogowanych; zapis wyłącznie service_role (brak polityk zapisu)
create policy "authenticated read" on public.fx_rates
  for select to authenticated using (true);
