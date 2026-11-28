"""
Run the whole CloudDesk project end to end (fictional company, synthetic data):

  generate -> validate raw -> load DuckDB -> dbt build (models + tests) -> SQL analyses -> EDA -> A/B test
  -> churn model -> MRR forecast -> export for Power BI -> insights report -> data dictionary

Usage:  python run_pipeline.py              full dataset (~27k accounts)
        python run_pipeline.py --small      ~15% sample, used by CI
        python run_pipeline.py --from dbt   resume from a step (names: see STEPS)
"""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SMALL = "--small" in sys.argv
PY = sys.executable
STEPS = [
    ("generate", "Generate synthetic data", [PY, "scripts/generate_data.py"] + (["--small"] if SMALL else []), None),
    ("validate", "Validate raw data (26 integrity checks)", [PY, "scripts/validate_raw.py"], None),
    ("load", "Load raw CSVs into DuckDB", [PY, "scripts/load_raw.py"], None),
    # dbt runs from inside saas_dbt/ so the relative warehouse path in profiles.yml resolves
    ("dbt", "dbt build (models + tests)", ["dbt", "build", "--profiles-dir", "."], "saas_dbt"),
    ("sql", "Run SQL analyses", [PY, "scripts/run_sql_analyses.py"], None),
    ("eda", "Exploratory data analysis", [PY, "analysis/eda.py"], None),
    ("ab_test", "A/B test readout", [PY, "analysis/ab_test.py"], None),
    ("churn", "Churn model", [PY, "analysis/churn_model.py"], None),
    ("forecast", "MRR forecast", [PY, "analysis/forecast_mrr.py"], None),
    ("export", "Export marts for Power BI + validation targets", [PY, "scripts/export_marts.py"], None),
    ("insights", "Business insights report", [PY, "analysis/business_insights.py"], None),
    ("dictionary", "Data dictionary", [PY, "scripts/build_data_dictionary.py"], None),
]

start = 0
if "--from" in sys.argv:
    name = sys.argv[sys.argv.index("--from") + 1]
    start = [s[0] for s in STEPS].index(name)

t_all = time.time()
for i, (_, title, cmd, cwd) in enumerate(STEPS[start:], start + 1):
    print(f"\n=== [{i}/{len(STEPS)}] {title} ===", flush=True)
    t0 = time.time()
    # PYTHONUTF8=1: write every report as UTF-8 on all platforms (Windows otherwise defaults to cp1252)
    env = {**os.environ, "PYTHONUTF8": "1"}
    if subprocess.run(cmd, cwd=ROOT / cwd if cwd else ROOT, env=env).returncode != 0:
        sys.exit(f"Step failed: {title}")
    print(f"--- done in {time.time() - t0:.1f}s", flush=True)
print(f"\nPipeline finished in {time.time() - t_all:.0f}s. Refresh Power BI to pick up data/marts/*.parquet")
