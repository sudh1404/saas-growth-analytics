-- Active customers in the KPI table at the snapshot month must equal active accounts in dim_accounts.
select k.active_customers, d.n
from {{ ref('agg_kpis_monthly') }} k,
     (select count(*) as n from {{ ref('dim_accounts') }} where lifecycle_status = 'active') d
where k.month = date_trunc('month', date '{{ var("snapshot_date") }}')
  and k.active_customers <> d.n
