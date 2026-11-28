"""
Export the warehouse for Power BI.

1. Every table in the `marts` schema -> data/marts/<table>.parquet  (Python outputs such as churn_scores.parquet,
   mrr_forecast.parquet and ab_test_summary.parquet are written to the same folder by the analysis scripts).
2. Optional CSV copies (--csv) for tools that cannot read Parquet.
3. powerbi/validation_targets.csv: the KPI values the finished dashboard must show, computed here in SQL with the
   SAME definitions as the DAX measures in powerbi/dax_measures.dax. Use it to check the report after building it.
"""
import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "warehouse" / "saas.duckdb"
OUT = ROOT / "data" / "marts"
PBI = ROOT / "powerbi"

TARGETS_SQL = """
with snap as (select max(month) as m from marts.fct_mrr),
base as (
    select account_id, mrr as m0 from marts.fct_mrr, snap
    where month = snap.m - interval 12 month and mrr > 0
),
nowm as (select account_id, mrr as m1 from marts.fct_mrr, snap where month = snap.m)
select 'Executive' as page, 'MRR (Dec 2025)' as kpi, 'no filters' as filter_context,
       (select sum(mrr) from marts.fct_mrr, snap where month = snap.m) as expected_value
union all select 'Executive', 'ARR (Dec 2025)', 'no filters', 12 * (select sum(mrr) from marts.fct_mrr, snap where month = snap.m)
union all select 'Executive', 'Active Customers (Dec 2025)', 'no filters',
       (select count(*) from marts.fct_mrr, snap where month = snap.m and is_active)
union all select 'Executive', 'Total Customers (ever paid)', 'no filters',
       (select count(*) from marts.dim_accounts where is_paying_customer)
union all select 'Executive', 'MRR Growth % (Dec vs Nov 2025)', 'no filters',
       (select mrr_growth_rate from marts.agg_kpis_monthly, snap where month = snap.m)
union all select 'Executive', 'Customer Churn Rate (Dec 2025, monthly)', 'month = Dec 2025',
       (select logo_churn_rate from marts.agg_kpis_monthly, snap where month = snap.m)
union all select 'Executive', 'Customer Churn Rate (2025 avg monthly)', 'year = 2025',
       (select count(*) filter (where movement_type = 'churn') * 1.0 / count(*) filter (where prev_mrr > 0)
        from marts.fct_mrr where year(month) = 2025)
union all select 'Executive', 'NRR 12m (Dec 2025)', 'no filters',
       (select sum(coalesce(m1, 0)) / sum(m0) from base left join nowm using (account_id))
union all select 'Retention', 'GRR 12m (Dec 2025)', 'no filters',
       (select sum(least(coalesce(m1, 0), m0)) / sum(m0) from base left join nowm using (account_id))
union all select 'Executive', 'CAC paid channels (all time)', 'no filters',
       (select sum(spend) / sum(new_customers) filter (where channel in ('paid_search','paid_social','content','partner'))
        from marts.fct_marketing_daily)
union all select 'Acquisition', 'Total Signups (all time)', 'no filters', (select count(*) from marts.dim_accounts)
union all select 'Acquisition', 'Activated Customers (all time)', 'no filters',
       (select count(*) from marts.dim_accounts where is_activated)
union all select 'Acquisition', 'Paying Customers from signups (all time)', 'no filters',
       (select count(*) from marts.dim_accounts where is_paying_customer)
union all select 'Acquisition', 'Overall Conversion (signup -> paid)', 'no filters',
       (select avg(is_paying_customer::int) from marts.dim_accounts)
union all select 'Acquisition', 'Total Signups', 'channel = paid_search',
       (select count(*) from marts.dim_accounts where acquisition_channel = 'paid_search')
union all select 'Retention', 'High-Risk Customers', 'no filters', null
union all select 'Revenue', 'ARPA (Dec 2025)', 'no filters', (select arpa from marts.agg_kpis_monthly, snap where month = snap.m)
union all select 'Revenue', 'LTV (all time, paid channels)', 'channel type = Paid',
       (select avg(m.mrr) filter (where m.is_active) * {gm}
               / (count(*) filter (where m.movement_type = 'churn') * 1.0 / count(*) filter (where m.prev_mrr > 0))
        from marts.fct_mrr m join marts.dim_accounts a using (account_id)
        where a.acquisition_channel in ('paid_search','paid_social','content','partner'))
union all select 'Revenue', 'CAC', 'channel = paid_search',
       (select sum(spend) / sum(new_customers) from marts.fct_marketing_daily where channel = 'paid_search')
union all select 'Revenue', 'LTV/CAC', 'channel = paid_search',
       (select ltv_to_cac from marts.agg_channel_performance where channel = 'paid_search')
union all select 'Revenue', 'New MRR (2025)', 'year = 2025',
       (select sum(new_mrr) from marts.agg_mrr_bridge_monthly where year(month) = 2025)
union all select 'Revenue', 'Expansion MRR (2025)', 'year = 2025',
       (select sum(expansion_mrr) from marts.agg_mrr_bridge_monthly where year(month) = 2025)
union all select 'Revenue', 'Contraction MRR (2025)', 'year = 2025',
       (select sum(contraction_mrr) from marts.agg_mrr_bridge_monthly where year(month) = 2025)
union all select 'Revenue', 'Churned MRR (2025)', 'year = 2025',
       (select sum(churned_mrr) from marts.agg_mrr_bridge_monthly where year(month) = 2025)
"""


def main(csv: bool = False):
    OUT.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB), read_only=True) as con:
        tables = [r[0] for r in con.execute(
            "select table_name from information_schema.tables where table_schema = 'marts' order by 1").fetchall()]
        for t in tables:
            con.execute(f"COPY (select * from marts.{t} order by all) TO '{(OUT / f'{t}.parquet').as_posix()}' (FORMAT parquet)").fetchall()
            if csv:
                con.execute(f"COPY (select * from marts.{t} order by all) TO '{(OUT / f'{t}.csv').as_posix()}' (HEADER, DELIMITER ',')").fetchall()
            n = con.execute(f"select count(*) from marts.{t}").fetchall()[0][0]
            print(f"exported {t + '.parquet':<36} {n:>8,} rows")
        gm = con.execute("select gross_margin from marts.agg_channel_performance limit 1").fetchall()[0][0]
        targets = con.sql(TARGETS_SQL.format(gm=gm)).df()

    scores = OUT / "churn_scores.parquet"
    if scores.exists():
        s = pd.read_parquet(scores)
        targets.loc[targets.kpi == "High-Risk Customers", "expected_value"] = int((s.risk_tier == "High").sum())
        if csv:
            s.to_csv(OUT / "churn_scores.csv", index=False)
    for extra in ["mrr_forecast", "ab_test_summary"]:
        if csv and (OUT / f"{extra}.parquet").exists():
            pd.read_parquet(OUT / f"{extra}.parquet").to_csv(OUT / f"{extra}.csv", index=False)
    PBI.mkdir(exist_ok=True)
    targets["expected_value"] = targets.expected_value.astype(float).round(4)
    targets.to_csv(PBI / "validation_targets.csv", index=False)
    print(f"\nwrote powerbi/validation_targets.csv ({len(targets)} KPI checks)")
    print(f"Power BI data folder: {OUT}")


if __name__ == "__main__":
    main("--csv" in sys.argv)
