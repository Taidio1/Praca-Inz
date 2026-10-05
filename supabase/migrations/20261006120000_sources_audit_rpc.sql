-- Odczyt audytu źródeł dla UI (spec 2026-10-05 §6). security invoker: RLS wywołującego.

create or replace function public.sources_page(
  p_asset_ids uuid[],
  p_threshold numeric,
  p_status text default 'all',
  p_before_ts timestamptz default null,
  p_before_id uuid default null,
  p_limit int default 30,
  p_asset_filter uuid default null
)
returns table (
  id uuid, source text, url text, title text, snippet text,
  published_at timestamptz, fetched_at timestamptz, duplicate_of uuid,
  relevance_done boolean, assessments jsonb
)
language sql stable security invoker set search_path = public
as $$
  with assess as (
    select r.item_id,
      jsonb_agg(jsonb_build_object(
        'asset_id', r.asset_id, 'ticker', a.ticker, 'score', r.score, 'method', r.method,
        'reason', r.reason, 'match_score', r.match_score, 'embedding_score', r.embedding_score
      ) order by r.score desc) as assessments,
      max(r.score) as top
    from item_relevance r
    join assets a on a.id = r.asset_id
    where r.asset_id = any(p_asset_ids)
      and (p_asset_filter is null or r.asset_id = p_asset_filter)
    group by r.item_id
  )
  select s.id, s.source, s.url, s.title, s.snippet, s.published_at, s.fetched_at,
    s.duplicate_of, s.relevance_done_at is not null, coalesce(x.assessments, '[]'::jsonb)
  from source_items s
  left join assess x on x.item_id = s.id
  where s.duplicate_of is null
    and (p_before_ts is null or (s.fetched_at, s.id) < (p_before_ts, p_before_id))
    and case p_status
      when 'passed' then coalesce(x.top >= p_threshold, false)
      when 'rejected' then coalesce(x.top < p_threshold, false)
      when 'unmatched' then x.item_id is null and s.relevance_done_at is not null
      else (p_asset_filter is null or x.item_id is not null)
    end
  order by s.fetched_at desc, s.id desc
  limit least(greatest(p_limit, 1), 100);
$$;

create or replace function public.sources_funnel(
  p_since timestamptz, p_asset_ids uuid[], p_threshold numeric
)
returns jsonb
language sql stable security invoker set search_path = public
as $$
  with items as (
    select id, duplicate_of, relevance_done_at from source_items where fetched_at >= p_since
  ),
  rel as (
    select r.item_id, max(r.score) as top
    from item_relevance r join items i on i.id = r.item_id
    where r.asset_id = any(p_asset_ids)
    group by r.item_id
  )
  select jsonb_build_object(
    'fetched', (select count(*) from items),
    'duplicates', (select count(*) from items where duplicate_of is not null),
    'scored', (select count(*) from items
               where duplicate_of is null and relevance_done_at is not null),
    'candidates', (select count(*) from rel),
    'passed', (select count(*) from rel where top >= p_threshold),
    'rejected', (select count(*) from rel where top < p_threshold),
    'unmatched', (select count(*) from items i
                  where i.duplicate_of is null and i.relevance_done_at is not null
                    and not exists (select 1 from rel where rel.item_id = i.id)),
    'sent_to_llm', (select count(*) from insight_items ii
                    join insights n on n.id = ii.insight_id
                    where n.created_at >= p_since and n.asset_id = any(p_asset_ids)),
    'insights', (select count(*) from insights
                 where created_at >= p_since and asset_id = any(p_asset_ids)),
    'cost_usd', (select coalesce(sum(cost_usd), 0) from llm_runs where created_at >= p_since)
  );
$$;

grant execute on function public.sources_page(uuid[], numeric, text, timestamptz, uuid, int, uuid)
  to authenticated;
grant execute on function public.sources_funnel(timestamptz, uuid[], numeric) to authenticated;
