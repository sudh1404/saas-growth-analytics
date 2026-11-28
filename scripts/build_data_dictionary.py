"""
Generate docs/data_dictionary.md from the live warehouse so the documentation can never drift from the data.

For every raw table, every mart and every Python output it lists: grain, row count, columns, data type,
null %, and a business description. Descriptions come from the dbt manifest (models/*.yml) when present,
otherwise from COLUMN_DOCS below.
"""
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "warehouse" / "saas.duckdb"
MARTS = ROOT / "data" / "marts"
MANIFEST = ROOT / "saas_dbt" / "target" / "manifest.json"

COLUMN_DOCS = {
    "account_id": "Account (customer company) identifier; primary key of accounts / dim_accounts.",
    "signup_date": "Date the account signed up and started its 14-day free trial.",
    "signup_month": "First day of the signup month.",
    "acquisition_channel": "Marketing channel that acquired the account: organic, paid_search, paid_social, referral, content, partner.",
    "channel": "Acquisition / marketing channel (same values as acquisition_channel).",
    "country": "Customer country (canonicalised in staging; 'Unknown' if missing).",
    "company_size": "Employee band: 1-10, 11-50, 51-200, 201+ ('Unknown' if missing).",
    "customer_segment": "SMB (1-50 employees), Mid-Market (51-200), Enterprise (201+).",
    "industry": "Customer industry.",
    "pricing_page_variant": "A/B test arm (A control, B annual-discount banner); NULL outside Jul-Sep 2025.",
    "plan_id": "Subscription plan identifier (1 Free, 2 Starter, 3 Pro, 4 Business).",
    "plan_name": "Plan name.", "monthly_price": "List price per month (USD).", "plan_tier": "Ordinal plan level 0-3.",
    "max_seats": "Seat limit of the plan (NULL = unlimited).",
    "event_id": "Event identifier.", "event_name": "Event type (signed_up, onboarding_completed, project_created, teammate_invited, subscription_started, support_ticket_opened).",
    "event_ts": "Event timestamp (UTC).", "event_date": "Event date.", "event_month": "First day of the event month.",
    "subscription_id": "Subscription period identifier; a new row starts on every plan change.",
    "start_date": "First day the subscription period is active.", "end_date": "Day the period ended (NULL = still active).",
    "mrr": "Monthly recurring revenue (USD) - for fct_mrr, MRR active at month end.",
    "start_reason": "Why the period started: new, upgrade, downgrade.", "end_reason": "Why it ended: upgraded, downgraded, churned.",
    "churn_reason": "Stated churn reason (payment_failure = involuntary).", "churn_type": "voluntary / involuntary.",
    "is_active": "True if the subscription / account-month is active.",
    "invoice_id": "Invoice identifier.", "invoice_date": "Billing date.", "invoice_month": "First day of the billing month.",
    "due_date": "Payment due date.", "amount": "Amount (USD).", "status": "Final or attempt status.",
    "is_paid": "True if the invoice was collected.", "payment_id": "Payment attempt identifier.",
    "attempt_number": "1 = initial charge, 2-3 = dunning retries.", "attempted_at": "Attempt timestamp.",
    "failure_reason": "card_declined, insufficient_funds, expired_card (NULL if succeeded).", "is_success": "True if the attempt succeeded.",
    "usage_month": "First day of the usage month.", "active_seats": "Active user seats in the month.",
    "sessions": "Product sessions in the month (NULL during the Mar-2025 tracking outage).",
    "sessions_per_seat": "sessions / active_seats - engagement intensity comparable across company sizes.",
    "spend_date": "Date of the paid-media spend.", "campaign": "Paid campaign name.", "impressions": "Ad impressions.",
    "clicks": "Ad clicks.", "spend": "Paid-media spend (USD).", "cpc": "Cost per click.", "ctr": "Click-through rate.",
    "traffic_date": "Date of web traffic.", "visitors": "Unique website visitors.", "pricing_page_views": "Pricing-page views.",
    "date": "Calendar date.", "month": "First day of the month.", "signups": "Accounts that signed up.",
    "new_customers": "New paying customers (first payment in the period).",
    "is_onboarded": "Completed onboarding.", "has_created_project": "Created a first project.",
    "is_activated": "Invited a teammate (activation / 'aha' moment).", "is_paying_customer": "Ever had a paid subscription.",
    "first_paid_date": "Date of the first payment.", "cohort_month": "Month of the first payment (acquisition cohort).",
    "first_plan_id": "Plan chosen at first payment.", "current_plan_id": "Plan at the snapshot (NULL if churned / never paid).",
    "current_mrr": "MRR at the snapshot date.", "churned_date": "Date the customer churned.",
    "lifecycle_status": "never_paid / active / churned.", "tenure_months": "Months from first payment to churn or snapshot.",
    "upgrades": "Number of upgrades.", "downgrades": "Number of downgrades.", "revenue_to_date": "Collected revenue (USD).",
    "failed_payment_attempts": "Failed payment attempts (all time).", "unpaid_invoices": "Invoices never collected.",
    "support_tickets": "Support tickets opened.", "prev_mrr": "MRR at the end of the previous month.",
    "mrr_change": "mrr - prev_mrr.", "movement_type": "new, expansion, contraction, churn, reactivation, retained.",
    "months_since_start": "Months since the account's first paid month.",
    "step_order": "Funnel step 1-5.", "step_name": "Funnel step label.", "reached_at": "When the account reached the step.",
    "opening_mrr": "MRR at the start of the month.", "new_mrr": "MRR from new customers.", "expansion_mrr": "MRR added by upgrades.",
    "reactivation_mrr": "MRR from returning customers.", "contraction_mrr": "MRR lost to downgrades (negative).",
    "churned_mrr": "MRR lost to churn (negative).", "net_new_mrr": "Sum of all movements.", "closing_mrr": "MRR at month end.",
    "arr": "Annual recurring revenue = 12 x MRR.", "active_customers": "Paying customers at month end.",
    "churned_customers": "Customers lost in the month.", "logo_churn_rate": "churned_customers / customers paying at start of month.",
    "mrr_growth_rate": "net_new_mrr / opening_mrr.", "gross_mrr_churn_rate": "(churned + contraction MRR) / opening MRR.",
    "arpa": "Average revenue per account = MRR / active customers.", "arpu": "MRR per active seat.",
    "nrr_12m": "Net revenue retention, trailing 12 months.", "grr_12m": "Gross revenue retention, trailing 12 months.",
    "marketing_spend": "Paid-media spend.", "paid_channel_new_customers": "New customers from paid channels.",
    "blended_cac": "All spend / all new customers.", "paid_cac": "Spend / new customers from paid channels.",
    "cohort_customers": "Customers in the cohort (Month 0).", "cohort_start_mrr": "Cohort MRR in Month 0.",
    "retained_customers": "Cohort customers still paying at month k.", "retained_mrr": "Their MRR at month k.",
    "logo_retention": "retained_customers / cohort_customers.", "revenue_retention": "retained_mrr / cohort_start_mrr.",
    "channel_type": "Paid / Unpaid.", "channel_name": "Display name.", "is_paid": "True for channels with media spend.",
    "cac": "Customer acquisition cost.", "ltv": "Lifetime value = ARPA x gross margin / monthly churn.",
    "ltv_to_cac": "LTV / CAC.", "cac_payback_months": "CAC / (ARPA x gross margin).",
    "churn_probability": "Model probability of churning within 3 months.", "risk_tier": "Low / Medium / High.",
    "risk_reasons": "Rule-based reason codes.", "recommended_action": "Suggested Customer Success action.",
    "expected_mrr_loss": "churn_probability x mrr.", "series": "Actual or Forecast.", "lower_80": "80% interval lower bound.",
    "upper_80": "80% interval upper bound.", "lower_95": "95% interval lower bound.", "upper_95": "95% interval upper bound.",
    "A": "Value for control (A).", "B": "Value for treatment (B).", "metric": "A/B test metric.",
    "difference": "B minus A.", "p_value": "Two-sided p-value of the test for that metric.", "decision": "Ship / do not ship / continue testing.",
    "model": "Forecast model used.", "scored_at": "Snapshot date the churn score refers to.",
    "cumulative_revenue_share": "Running share of total collected revenue (customers sorted by revenue).",
    "current_plan": "Plan name at the snapshot.", "engagement_segment": "Low / Medium / High engagement tercile.",
    "engagement_tercile": "1 (low) - 3 (high) by sessions per seat, last 3 complete months.",
    "failed_attempts_90d": "Failed payment attempts in the 90 days before the snapshot.",
    "failed_payment_attempts_90d": "Failed payment attempts in the 90 days before the snapshot.",
    "gross_margin": "Assumed gross margin (dbt var gross_margin).", "monthly_logo_churn": "Churn events / customer-months at risk.",
    "revenue_quartile": "1 = top 25% by collected revenue.", "revenue_segment": "Revenue quartile label.",
    "rule_based_risk": "Low / Medium / High from rule_risk_score (transparent SQL baseline).",
    "rule_risk_score": "Points: usage down 30%+ (2), failed payment 90d (2), 2+ tickets 90d (1), not activated (1), tenure < 3m (1).",
    "sessions_per_seat_3m": "Avg sessions per seat over the last 3 complete usage months (-1 in the model = no history).",
    "share_of_current_mrr": "Channel share of snapshot MRR.", "signup_to_paid_rate": "New customers / signups.",
    "support_tickets_90d": "Support tickets in the 90 days before the snapshot.", "tickets_90d": "Support tickets in the 90 days before the snapshot.",
    "tenure_band": "Tenure bucket.", "usage_trend": "Sessions/seat last 3 months / prior 3 months (<1 = declining).",
    "visit_to_signup_rate": "Signups / visitors.", "is_actual_period": "True up to the snapshot date; False on forecast dates.",
    "is_weekend": "Saturday or Sunday.", "day_of_week": "0 = Sunday ... 6 = Saturday.", "month_name": "Short month name.",
    "month_num": "Month number 1-12.", "month_start": "First day of the month (use as the monthly axis).",
    "quarter": "Quarter 1-4.", "year": "Calendar year.", "year_month": "YYYY-MM label.", "year_quarter": "e.g. Q1 2025.",
}
GRAIN = {
    "plans": "one row per plan", "accounts": "one row per signed-up account", "web_traffic": "date x channel",
    "marketing_spend": "date x channel x campaign (with duplicates)", "events": "one row per event (with duplicates)",
    "subscriptions": "one row per subscription period", "invoices": "one row per monthly invoice",
    "payments": "one row per payment attempt", "usage_monthly": "account x month",
    "dim_accounts": "one row per account", "dim_plans": "one row per plan", "dim_channel": "one row per channel",
    "dim_date": "one row per day", "fct_mrr": "account x month", "fct_funnel_steps": "account x funnel step reached",
    "fct_invoices": "one row per invoice", "fct_payments": "one row per payment attempt", "fct_usage_monthly": "account x month",
    "fct_product_events": "one row per de-duplicated event", "fct_marketing_daily": "date x channel",
    "fct_campaign_daily": "date x channel x campaign", "agg_mrr_bridge_monthly": "one row per month",
    "agg_kpis_monthly": "one row per month", "agg_cohort_retention": "cohort month x channel x months since start",
    "agg_channel_performance": "one row per channel", "agg_customer_segments": "one row per active customer at snapshot",
    "churn_scores": "one row per active customer at 2025-12-31 (Python churn model)",
    "mrr_forecast": "month x series (Actual / Forecast) (Python forecast)",
    "ab_test_summary": "one row per A/B metric (Python A/B readout)",
}


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"nodes": {}, "sources": {}}
    docs, model_desc = {}, {}
    for node in list(manifest["nodes"].values()) + list(manifest["sources"].values()):
        if node.get("resource_type") in ("model", "source"):
            model_desc[node["name"]] = node.get("description", "")
            for c, meta in node.get("columns", {}).items():
                if meta.get("description"):
                    docs[(node["name"], c)] = meta["description"]

    out = ["# Data dictionary", "",
           "> Generated by `scripts/build_data_dictionary.py` from the live warehouse. CloudDesk is fictional; all data is synthetic.",
           "", "Layers: **raw** (CSV as generated) -> **staging** (cleaned views) -> **intermediate** -> **marts** (tables used by",
           "SQL analyses and Power BI) -> **Python outputs** (model results exported next to the marts).", ""]
    with duckdb.connect(str(DB), read_only=True) as con:
        sections = [("Raw layer (schema `raw`)", "raw"), ("Marts (schema `marts`)", "marts")]
        for title, schema in sections:
            out += [f"## {title}", ""]
            tables = [r[0] for r in con.execute(
                f"select table_name from information_schema.tables where table_schema='{schema}' order by 1").fetchall()]
            for t in tables:
                out += table_doc(con, f"{schema}.{t}", t, docs, model_desc)
        out += ["## Python outputs (data/marts/*.parquet)", ""]
        for t in ["churn_scores", "mrr_forecast", "ab_test_summary"]:
            f = MARTS / f"{t}.parquet"
            if f.exists():
                out += table_doc(con, f"read_parquet('{f.as_posix()}')", t, docs, model_desc)
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "data_dictionary.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("wrote docs/data_dictionary.md")


def table_doc(con, rel, name, docs, model_desc):
    cols = con.execute(f"describe select * from {rel}").fetchall()
    n = con.execute(f"select count(*) from {rel}").fetchall()[0][0]
    nulls = con.execute("select " + ", ".join(f'avg(("{c[0]}" is null)::int)' for c in cols) + f" from {rel}").fetchall()[0]
    lines = [f"### `{name}`", "", f"*Grain:* {GRAIN.get(name, '-')} &nbsp;|&nbsp; *Rows:* {n:,}"]
    if model_desc.get(name):
        lines += ["", model_desc[name].strip()]
    lines += ["", "| column | type | null % | description |", "|---|---|---:|---|"]
    for (c, typ, *_), nl in zip(cols, nulls):
        if c == "_loaded_at":
            desc = "Load timestamp added by scripts/load_raw.py."
        else:
            desc = docs.get((name, c)) or COLUMN_DOCS.get(c, "")
        lines.append(f"| {c} | {typ} | {100 * (nl or 0):.1f} | {desc} |")
    return lines + [""]


if __name__ == "__main__":
    main()
