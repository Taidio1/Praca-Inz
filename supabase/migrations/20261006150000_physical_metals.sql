-- Fizyczne metale szlachetne (złoto, srebro: sztabki, monety).
--  * assets.asset_type 'commodity'          — nowa klasa aktywów (XAU, XAG), ilość w uncjach
--                                             trojańskich, wycena po cenie spot za uncję
--  * portfolio_transactions.physical_form    — forma zakupu, tylko informacyjnie:
--                                             coin (moneta), bar (sztabka), other (inna)

alter table public.assets drop constraint assets_asset_type_check;
alter table public.assets
  add constraint assets_asset_type_check
    check (asset_type in ('crypto', 'stock', 'etf', 'commodity'));

alter table public.portfolio_transactions
  add column physical_form text
    constraint portfolio_transactions_physical_form_check
      check (physical_form in ('coin', 'bar', 'other'));
