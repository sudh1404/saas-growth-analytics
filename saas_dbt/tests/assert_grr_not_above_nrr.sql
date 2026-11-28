-- GRR caps each account at its starting MRR, so it can never exceed NRR or 100%.
select * from {{ ref('agg_kpis_monthly') }}
where grr_12m > nrr_12m + 1e-9 or grr_12m > 1 + 1e-9
