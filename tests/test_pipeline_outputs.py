"""
Integration tests for the pipeline outputs (run after `python run_pipeline.py`, full or --small).
They check business logic end to end, complementing the dbt data tests:
    pytest -q
"""
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "warehouse" / "saas.duckdb"
MARTS = ROOT / "data" / "marts"
pytestmark = pytest.mark.skipif(not DB.exists(), reason="run `python run_pipeline.py` first")


@pytest.fixture(scope="module")
def con():
    with duckdb.connect(str(DB), read_only=True) as c:
        yield c


def q(con, sql):
    return con.sql(sql).df()


def test_mrr_bridge_reconciles(con):
    b = q(con, "select * from marts.agg_mrr_bridge_monthly order by month")
    movements = b[["new_mrr", "expansion_mrr", "reactivation_mrr", "contraction_mrr", "churned_mrr"]].sum(axis=1)
    assert np.allclose(b.opening_mrr + movements, b.closing_mrr)
    assert np.allclose(b.opening_mrr.iloc[1:].values, b.closing_mrr.iloc[:-1].values)


def test_nrr_matches_independent_python_calculation(con):
    m = q(con, "select account_id, month, mrr from marts.fct_mrr")
    last = m.month.max()
    base = m[(m.month == last - pd.DateOffset(months=12)) & (m.mrr > 0)].set_index("account_id").mrr
    now = m[m.month == last].set_index("account_id").mrr.reindex(base.index).fillna(0)
    kpi = q(con, "select nrr_12m, grr_12m from marts.agg_kpis_monthly order by month desc limit 1").iloc[0]
    assert now.sum() / base.sum() == pytest.approx(kpi.nrr_12m, rel=1e-9)
    assert np.minimum(now, base).sum() / base.sum() == pytest.approx(kpi.grr_12m, rel=1e-9)


def test_arr_is_twelve_times_mrr(con):
    k = q(con, "select mrr, arr from marts.agg_kpis_monthly")
    assert np.allclose(k.arr, 12 * k.mrr)


def test_cac_ltv_definition(con):
    p = q(con, "select * from marts.agg_channel_performance where cac is not null")
    assert np.allclose(p.ltv, p.arpa * p.gross_margin / p.monthly_logo_churn)
    assert np.allclose(p.ltv_to_cac, p.ltv / p.cac)
    unpaid = q(con, "select cac from marts.agg_channel_performance where channel in ('organic','referral')")
    assert unpaid.cac.isna().all()


def test_funnel_rates_are_valid(con):
    f = q(con, "select * from marts.fct_funnel_steps")
    counts = f.groupby("step_order").account_id.nunique().sort_index()
    assert counts.iloc[:4].is_monotonic_decreasing      # steps 1-4 are sequential


def test_churn_scores_are_valid_probabilities():
    s = pd.read_parquet(MARTS / "churn_scores.parquet")
    assert s.account_id.is_unique
    assert s.churn_probability.between(0, 1).all()
    assert set(s.risk_tier) <= {"Low", "Medium", "High"}
    # tiers are ordered by probability
    med = s.groupby("risk_tier").churn_probability.median()
    assert med.get("Low", 0) < med.get("Medium", 1) < med.get("High", 2)


def test_churn_model_is_out_of_time():
    r = json.loads((ROOT / "reports" / "churn_model" / "churn_model_results.json").read_text(encoding="utf-8"))
    tr_end = r["splits"]["train"]["cutoffs"].split(" .. ")[1]
    va_start, va_end = r["splits"]["validation"]["cutoffs"].split(" .. ")
    te_start = r["splits"]["test"]["cutoffs"].split(" .. ")[0]
    assert tr_end < va_start <= va_end < te_start
    # labels of the latest training cutoff (3-month window) must be observable before test cutoffs start
    assert pd.Timestamp(tr_end) + pd.DateOffset(months=3) <= pd.Timestamp(te_start)


def test_forecast_shape_and_intervals():
    f = pd.read_parquet(MARTS / "mrr_forecast.parquet")
    fc = f[f.series == "Forecast"].sort_values("month")
    assert len(fc) == 7                                   # anchor month + 6 forecast months
    assert (fc.lower_80 <= fc.mrr).all() and (fc.mrr <= fc.upper_80).all()
    assert (fc.lower_95 <= fc.lower_80).all() and (fc.upper_80 <= fc.upper_95).all()


def test_ab_test_has_no_srm_and_a_decision():
    r = json.loads((ROOT / "reports" / "ab_test" / "ab_test_results.json").read_text(encoding="utf-8"))
    assert r["sample"]["srm_ok"]
    assert r["decision"]["recommendation"] in {"SHIP", "DO NOT SHIP", "CONTINUE TESTING"}
    lo, hi = r["primary"]["abs_lift_ci95"]
    assert lo <= r["primary"]["abs_lift"] <= hi


def test_powerbi_validation_targets_complete():
    t = pd.read_csv(ROOT / "powerbi" / "validation_targets.csv")
    assert t.expected_value.notna().all()
    assert {"Executive", "Acquisition", "Retention", "Revenue"} <= set(t.page)
