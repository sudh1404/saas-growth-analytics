# Power BI report specification - CloudDesk SaaS Growth

> Fictional company, synthetic data. Measures referenced below are defined in `dax_measures.dax`; business definitions
> are in `docs/metric_definitions.md`. Screenshots of the finished pages are in `reports/figures/dashboard/`.

## Global design
- **Canvas** 1280 x 720 (16:9). Grid: 16 px margins, 12 px gutters. Page background `#F4F6F9`, visuals white with 8 px radius.
- **Header row (y 0-56):** page title (Segoe UI Semibold 18, `#1F3B5C`), subtitle with data-as-of date, navigation buttons
  to the other three pages (page navigator, top right).
- **Slicer row (y 60-104):** Date range (between slider on `dim_date[date]`), Country, Acquisition channel, Plan, Company size
  (dropdowns, multi-select, "Select all" on). Synced across pages via *Sync slicers*.
- **KPI row (y 112-212):** cards (new "Card" visual), each with a reference label for MoM change where relevant.
- **Charts (y 220-704):** two rows of charts.
- **Colours:** categorical order from the theme is fixed per entity - Organic blue, Paid search orange, Paid social aqua,
  Referral yellow, Content pink, Partner green; plans Starter blue / Pro orange / Business aqua; risk tiers use the
  status colours (Low green, Medium amber, High red) **with labels**, never colour alone.
- **Rules:** no dual-axis charts; data labels on bars where a value matters; one-line chart titles that state the question.
- **Accessibility:** alt text on every visual (template: "<chart type> showing <measure> by <dimension>"); tab order set
  top-left to bottom-right; every chart has *Show as table* available.

---

## Page 1 - Executive Overview
**Question:** Is the business growing, and is growth healthy?

| # | Visual | Fields | Notes |
|---|---|---|---|
| K1-K8 | Cards | `Total Customers`, `Active Customers`, `MRR`, `ARR`, `MRR Growth %`, `Customer Churn Rate`, `NRR`, `CAC` | MRR/ARR/Active/NRR evaluate at the last month in the date range; churn rate = average monthly churn over the range |
| 1 | Line chart "MRR trend" | X `dim_date[month_start]`, Y `MRR` | markers on, data label on last point |
| 2 | Clustered column "New vs churned customers" | X `dim_date[month_start]`, Y `New Customers`, `Churned Customers` | blue / orange |
| 3 | Bar "Revenue by plan" | Y `dim_plans[plan_name]`, X `MRR` | data labels; plan = plan held in that month |
| 4 | Filled map or bar "Revenue by country" | `dim_accounts[country]`, `MRR` | bar preferred for precision; map optional |
| 5 | Bar "Acquisition channel contribution" | Y `dim_channel[channel_name]`, X `MRR`, tooltip `Active Customers`, `New Customers` | sort descending |

Interactions: all visuals cross-filter each other; KPI cards are filter targets only.

## Page 2 - Acquisition and Funnel Performance
**Question:** Where do customers come from, and where do we lose them?

| # | Visual | Fields | Notes |
|---|---|---|---|
| K1-K5 | Cards | `Total Signups`, `Activated Customers`, `Paying Customers`, `Overall Conversion Rate`, `CAC` | funnel cards use signup date |
| 1 | Funnel "Customer acquisition funnel" | Category `fct_funnel_steps[step_name]` (sorted by `step_order`), Values `Funnel Accounts` | tooltip `Step Conversion %` |
| 2 | Bar "Funnel drop-off by step" | `fct_funnel_steps[step_name]`, `Step Drop-off %` | highlights the largest leak (Project -> Activated) |
| 3 | Clustered bar "Conversion by channel" | `dim_channel[channel_name]`, `Activation Rate`, `Overall Conversion Rate` | |
| 4 | Line "Signup trend" | X `dim_date[month_start]`, Y `Total Signups`, Legend `dim_channel[channel_name]` | |
| 5 | Scatter "Marketing spend vs acquired customers" | Details `dim_channel[channel_name]`, X `Marketing Spend`, Y `New Customers Acquired`, Size `CAC` | paid channels only (visual filter `dim_channel[is_paid] = True`). Replaces a dual-axis combo chart. |
| 6 | Table "Channel performance" | `dim_channel[channel_name]`, `Visitors`, `Visit to Signup %`, `Total Signups`, `Overall Conversion Rate`, `Marketing Spend`, `CAC`, `LTV/CAC` | conditional formatting (data bars) on CAC and LTV/CAC |

Interactions: Country / Company size slicers do **not** affect `Visitors`, `Marketing Spend`, `CAC` (traffic and spend are
only tracked by channel x date). Add a small info icon with this note next to the CAC card.

## Page 3 - Retention and Customer Health
**Question:** Who stays, who leaves, and who is at risk right now?

| # | Visual | Fields | Notes |
|---|---|---|---|
| K1-K5 | Cards | `Customer Retention Rate`, `Customer Churn Rate`, `GRR`, `NRR`, `High-Risk Customers` | |
| 1 | Matrix heatmap "Cohort retention" | Rows `dim_accounts[cohort_month]`, Columns `fct_mrr[months_since_start]` (visual filter 0-12), Values `Cohort Retention %` | background colour scale min `#CCE3FD` -> max `#0E3D7E`; measure ignores the date slicer by design |
| 2 | Line "Monthly churn trend" | X `dim_date[month_start]`, Y `Customer Churn Rate` | add average line (Analytics pane) |
| 3 | Donut or bar "Customer risk segmentation" | `churn_scores[risk_tier]`, `Scored Customers`, tooltip `MRR at Risk (High)` | colours: Low `#0AAC23`, Medium `#FBB315`, High `#DC3C3D`; labels on |
| 4 | Column "Churn probability distribution" | X `churn_scores[probability_bin]`, Y `Scored Customers`, Legend `risk_tier` | |
| 5 | Line "Customer engagement trend" | X `dim_date[month_start]`, Y `Avg Sessions per Seat` | Mar-2025 dip is a tracking outage - annotate |
| 6 | Line "Retention by acquisition channel" | X `fct_mrr[months_since_start]` (0-12), Y `Cohort Retention %`, Legend `dim_channel[channel_name]` | |
| 7 | Table "Customers to contact" | `churn_scores[account_id]`, `plan_name`, `mrr`, `churn_probability`, `risk_reasons`, `recommended_action` | visual filter risk_tier = High, sorted by `expected_mrr_loss` |

## Page 4 - Revenue and Growth
**Question:** Where does revenue growth come from, and is acquisition paying back?

| # | Visual | Fields | Notes |
|---|---|---|---|
| K1-K6 | Cards | `MRR`, `ARR`, `ARPA`, `CAC`, `LTV`, `LTV/CAC` | |
| 1 | Waterfall "MRR bridge" | Use a *Waterfall* with Category = a disconnected table `Bridge Step` (Opening, New, Expansion, Reactivation, Contraction, Churned) and a SWITCH measure, **or** a stacked column by month with `New MRR`, `Expansion MRR`, `Contraction MRR`, `Churned MRR` | see snippet below |
| 2 | Stacked column "Revenue by plan" | X `dim_date[month_start]`, Y `MRR`, Legend `dim_plans[plan_name]` | |
| 3 | Clustered column "Expansion vs contraction" | X `dim_date[month_start]`, Y `Expansion MRR`, `Lost MRR (Churn + Contraction)` | |
| 4 | Line "Actual vs forecast MRR" | X `dim_date[month_start]`, Y `Actual MRR (chart)`, `Forecast MRR`, error band `Forecast Lower 80%` / `Forecast Upper 80%` | Analytics pane > Error bars; forecast blank when a segment slicer is active |
| 5 | Bar "CAC by channel" | `dim_channel[channel_name]`, `CAC` | paid channels |
| 6 | Bar "LTV/CAC by channel" | `dim_channel[channel_name]`, `LTV/CAC` | constant line at 3 (benchmark) |

Waterfall helper (optional):
```dax
Bridge Step = DATATABLE ( "Step", STRING, "Order", INTEGER,
    { { "Opening", 1 }, { "New", 2 }, { "Expansion", 3 }, { "Reactivation", 4 }, { "Contraction", 5 }, { "Churned", 6 } } )

Bridge Value =
SWITCH ( SELECTEDVALUE ( 'Bridge Step'[Step] ),
    "Opening", [Opening MRR], "New", [New MRR], "Expansion", [Expansion MRR],
    "Reactivation", [Reactivation MRR], "Contraction", [Contraction MRR], "Churned", [Churned MRR] )
```
Add `[MRR]` as the waterfall total ("Closing MRR").

---

## Dashboard field dictionary
| Field / measure | Table | Meaning | Responds to |
|---|---|---|---|
| `MRR`, `ARR` | `_Measures` | MRR at the end of the latest month in the selection; ARR = 12 x MRR | Date, Country, Channel, Plan, Size |
| `MRR Growth %` | `_Measures` | MoM change of MRR at the latest selected month | all |
| `Total Customers` | `_Measures` | Customers who ever paid up to the latest selected month | all except start of date range |
| `Active Customers` | `_Measures` | Paying customers at the latest selected month | all |
| `New / Churned Customers` | `_Measures` | Count of new / churn movements in the selected months | all |
| `Customer Churn Rate` | `_Measures` | Average monthly logo churn = churn events / customer-months at risk | all |
| `Customer Retention Rate` | `_Measures` | 1 - monthly churn rate | all |
| `NRR`, `GRR` | `_Measures` | Trailing-12-month net / gross revenue retention at the latest selected month | all (plan = plan held that month) |
| `ARPA`, `ARPU` | `_Measures` | MRR per active account / per active seat | all |
| `Opening/New/Expansion/Contraction/Churned/Net New MRR` | `_Measures` | MRR bridge components over the selected months | all |
| `Total Signups`, `Activated Customers`, `Paying Customers` | `_Measures` | Accounts by **signup date** in the selection, and how many activated / paid | Date (signup), Country, Channel, Size |
| `Overall Conversion Rate` | `_Measures` | Paying / signups | as above |
| `Funnel Accounts`, `Step Conversion %`, `Step Drop-off %` | `_Measures` | Accounts reaching each step; conversion / loss vs previous step | as above |
| `Visitors`, `Visit to Signup %` | `_Measures` | Website visitors (channel x day) | Date, Channel only |
| `Marketing Spend`, `New Customers Acquired`, `CAC`, `Blended CAC` | `_Measures` | Paid spend; customers by first-payment date; spend / new paid-channel customers | Date, Channel only |
| `LTV`, `LTV/CAC`, `CAC Payback (months)` | `_Measures` | ARPA x 80% margin / monthly churn; ratio to CAC; months to recover CAC | Date, Channel (CAC part), all (LTV part) |
| `Cohort Retention %` | `_Measures` | Share of a first-payment cohort still paying k months later | all except Date |
| `High-Risk Customers`, `MRR at Risk (High)`, `Avg Churn Probability` | `_Measures` | From the churn model scored at 2025-12-31 | Country, Channel, Size (not Date) |
| `Forecast MRR`, `Forecast Lower/Upper 80%` | `_Measures` | Company-level 6-month MRR forecast and 80% interval | Date; blank under segment slicers |
| `dim_accounts[cohort_month]` | `dim_accounts` | Month of first payment | - |
| `fct_mrr[months_since_start]` | `fct_mrr` | Months since first payment (cohort age) | - |
| `churn_scores[risk_tier]` | `churn_scores` | High (p >= action threshold), Medium (>= base rate), Low | - |
| `churn_scores[risk_reasons]` | `churn_scores` | Rule-based reason codes for Customer Success | - |

Full column-level documentation: `docs/data_dictionary.md`.
