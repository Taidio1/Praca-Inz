insert into public.assets (ticker, name, asset_type, aliases) values
  ('BTC',  'Bitcoin',      'crypto', array['bitcoin', 'btc', 'xbt']),
  ('ETH',  'Ethereum',     'crypto', array['ethereum', 'ether', 'eth']),
  ('SOL',  'Solana',       'crypto', array['solana', 'sol']),
  ('AAPL', 'Apple Inc.',   'stock',  array['apple', 'aapl']),
  ('NVDA', 'NVIDIA Corp.', 'stock',  array['nvidia', 'nvda']),
  ('TSLA', 'Tesla Inc.',   'stock',  array['tesla', 'tsla']),
  ('MSFT', 'Microsoft',    'stock',  array['microsoft', 'msft']),
  ('SPY',  'S&P 500 ETF',  'etf',    array['sp500', 's&p 500', 'spy'])
on conflict (ticker, asset_type) do nothing;
