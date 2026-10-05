-- Cena zakupu (USD) podawana przez użytkownika przy dodawaniu pozycji.
-- Nullable: istniejące pozycje nie mają ceny zakupu; nowe wpisy wymuszane w API/UI.
alter table public.portfolio_positions
  add column avg_buy_price numeric check (avg_buy_price > 0);
