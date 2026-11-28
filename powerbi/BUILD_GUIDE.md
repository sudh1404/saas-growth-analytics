# Power BI build & refresh guide

> CloudDesk is a fictional company and all data is synthetic.
> The finished report is included: `powerbi/CloudDesk_SaaS_Growth.pbix` (open directly) and the same report as a
> Power BI Project in `powerbi/CloudDesk_Dashboard/` (text files for version control). This guide explains how it
> connects to the data, how to refresh it, and how to rebuild it from scratch.

## Quick start: open the included report
- **Just look at it:** open `powerbi/CloudDesk_SaaS_Growth.pbix`. The data is stored inside the file.
- **Refresh with new data:** run `python run_pipeline.py`, open the report, then *Home > Transform data > Edit parameters*.
  Set `DataFolder` to the absolute path of this repo's `data/marts/` folder, **with a trailing backslash**, then click **Refresh**.

| File | Purpose |
|---|---|
| `data/marts/*.parquet` | Model tables (created by `python run_pipeline.py`) |
| `powerbi/clouddesk_theme.json` | Colour-blind-safe report theme |
| `powerbi/dax_measures.dax` | All measures, loadable in one step via DAX query view |
| `powerbi/REPORT_SPEC.md` | Page layouts, visuals, fields, slicers, interactions, dashboard field dictionary |
| `powerbi/validation_targets.csv` | KPI values the finished report must show (computed in SQL) |
| `powerbi/CloudDesk_SaaS_Growth.pbix` | Finished report (data included) |
| `powerbi/CloudDesk_Dashboard/` | Same report as a Power BI Project (TMDL model + PBIR pages, text) |
| `reports/figures/dashboard/*.png` | Screenshots of the four pages |

---

## Rebuilding from scratch (optional)

## 1. Produce the data
```bash
python run_pipeline.py          # generates, loads, builds dbt, runs analyses, exports data/marts/*.parquet
```
Optional CSV copies: `python scripts/export_marts.py --csv`.

## 2. Connect Power BI to the exports
1. Open Power BI Desktop > **Blank report**. *View > Themes > Browse for themes* > `powerbi/clouddesk_theme.json`.
2. *Home > Transform data* > **New Parameter**: Name `DataFolder`, Type *Text*, Current value = the absolute path of
   `data/marts/` **including the trailing backslash**, e.g. `C:\projects\saas-growth-analytics\data\marts\`.
3. For each table below: *New Source > Blank Query*, open *Advanced Editor*, paste, and name the query exactly as the table:
   ```m
   let
       Source = Parquet.Document(File.Contents(DataFolder & "fct_mrr.parquet"))
   in
       Source
   ```
   Tables to load (14): `dim_accounts`, `dim_plans`, `dim_channel`, `dim_date`, `fct_mrr`, `fct_funnel_steps`,
   `fct_marketing_daily`, `fct_campaign_daily`, `fct_usage_monthly`, `fct_invoices`, `agg_channel_performance`,
   `churn_scores`, `mrr_forecast`, `ab_test_summary`.
   *(Tip: create the first query, then duplicate it and change only the file name.)*
4. Data types to confirm in Power Query: every `*_date`, `month`, `usage_month`, `cohort_month` = **Date**;
   `reached_at`, `scored_at` = Date/Time; `is_*` = True/False; money columns = Decimal (Fixed decimal for `mrr`, `spend` is fine).
5. In `churn_scores` add a column for the probability histogram:
   *Add Column > Custom Column* `probability_bin` = `Number.RoundDown([churn_probability] * 50) / 50` (2-point bins).
6. *Close & Apply*.

## 3. Data model (star schema)
Open *Model view*, delete any auto-detected relationships, then create these (single cross-filter direction, from the "1" side):

| From (1) | To (*) | Active | Notes |
|---|---|---|---|
| `dim_date[date]` | `fct_mrr[month]` | Yes | monthly fact keyed on first day of month |
| `dim_date[date]` | `fct_marketing_daily[date]` | Yes | |
| `dim_date[date]` | `fct_campaign_daily[date]` | Yes | |
| `dim_date[date]` | `fct_usage_monthly[usage_month]` | Yes | |
| `dim_date[date]` | `mrr_forecast[month]` | Yes | |
| `dim_date[date]` | `dim_accounts[signup_date]` | **No (inactive)** | used by funnel measures through `USERELATIONSHIP` |
| `dim_accounts[account_id]` | `fct_mrr[account_id]` | Yes | |
| `dim_accounts[account_id]` | `fct_funnel_steps[account_id]` | Yes | |
| `dim_accounts[account_id]` | `fct_usage_monthly[account_id]` | Yes | |
| `dim_accounts[account_id]` | `fct_invoices[account_id]` | Yes | |
| `dim_accounts[account_id]` | `churn_scores[account_id]` | Yes | set cardinality to *Many-to-one*, single direction |
| `dim_plans[plan_id]` | `fct_mrr[plan_id]` | Yes | plan **in that month** |
| `dim_channel[channel]` | `dim_accounts[acquisition_channel]` | Yes | snowflaked channel dimension |
| `dim_channel[channel]` | `fct_marketing_daily[channel]` | Yes | |
| `dim_channel[channel]` | `fct_campaign_daily[channel]` | Yes | |
| `dim_channel[channel]` | `agg_channel_performance[channel]` | Yes | one-to-one |

Then:
- Select `dim_date` > *Mark as date table* > column `date`.
- Sort `dim_date[month_name]` by `month_num`; sort `fct_funnel_steps[step_name]` by `step_order`.
- Hide all `*_id` foreign-key columns on fact tables and the dummy column of `_Measures`.

**Why the inactive signup relationship?** A date slicer must mean "revenue in this period" for MRR visuals but
"accounts that *signed up* in this period" for funnel visuals. Keeping the signup relationship inactive and turning it
on inside the funnel measures gives both behaviours from one slicer without ambiguous filter paths.

## 4. Load the measures
1. *Home > Enter data* > table name `_Measures` > *Load*.
2. Open **DAX query view**, paste `powerbi/dax_measures.dax`, click **Run**.
3. Click **Update model: Add new measures**. All 58 measures land in `_Measures`.
4. The query result shows the headline KPIs; compare them with `powerbi/validation_targets.csv` (no slicers applied).
5. Apply the formats noted in the comments (e.g. `MRR` = `$#,0`, rates = `0.0%`). Group measures into display folders
   (Revenue, Customers, Funnel, Unit economics, Retention, Health, Forecast) if you like.

## 5. Build the four pages
Follow `powerbi/REPORT_SPEC.md`: canvas 1280 x 720, page background from the theme, KPI cards in the top row,
slicers in one row under the title. Use *View > Sync slicers* so the Date, Country, Channel, Plan and Company size
slicers are shared across pages (Date synced everywhere; segment slicers synced except where noted).

## 6. Validate before publishing
| Check | How |
|---|---|
| KPI values | With no slicers, each card must equal `validation_targets.csv` (rounding aside). Then set the filter contexts listed in the file (e.g. `channel = paid_search`, `year = 2025`) and check those rows. |
| MRR bridge | `Opening MRR + Net New MRR = MRR` for any date range (add the three to a table to verify). |
| Filters | Change each slicer and confirm every visual responds or is intentionally excluded (see interaction notes in REPORT_SPEC). |
| Forecast | The forecast line must be blank when a country / channel / plan / size slicer is active (it is a company-level forecast). |

## 7. Refresh
1. Re-run `python run_pipeline.py` (regenerates data, rebuilds dbt, re-scores churn, re-forecasts, re-exports).
2. In Power BI Desktop click **Refresh**. Nothing else changes: queries read the same file names from `DataFolder`.
3. To move the project to another folder or machine: *Transform data > Edit parameters > DataFolder*.
4. Power BI Service: publish, then configure an on-premises data gateway (personal mode) pointing at the same folder for
   scheduled refresh, or store the parquet files in SharePoint/OneDrive and switch the source to `SharePoint.Files`.
