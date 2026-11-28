-- Daily channel spend in the mart must equal de-duplicated campaign spend (no rows lost or double counted).
select a.total, b.total
from (select sum(spend) as total from {{ ref('fct_marketing_daily') }}) a,
     (select sum(spend) as total from {{ ref('fct_campaign_daily') }}) b
where abs(a.total - b.total) > 0.01
