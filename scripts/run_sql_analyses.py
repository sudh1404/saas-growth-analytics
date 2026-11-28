"""
Execute every analysis in sql/*.sql against the warehouse, save each result to reports/sql_results/<name>.csv
and print a short preview. Exits 1 if any query fails, so CI catches broken SQL.

Usage:  python scripts/run_sql_analyses.py            (run all, short preview)
        python scripts/run_sql_analyses.py --verbose  (print every result in full)
"""
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "warehouse" / "saas.duckdb"
OUT = ROOT / "reports" / "sql_results"


def main(verbose: bool = False):
    OUT.mkdir(parents=True, exist_ok=True)
    failures = []
    files = sorted((ROOT / "sql").glob("*.sql"))
    with duckdb.connect(str(DB), read_only=True) as con:
        for f in files:
            t0 = time.time()
            try:
                df = con.sql(f.read_text(encoding="utf-8")).df()
            except Exception as e:  # noqa: BLE001 - report every failing query, then exit non-zero
                failures.append(f.name)
                print(f"FAIL {f.name}: {e}")
                continue
            df.to_csv(OUT / f"{f.stem}.csv", index=False)
            print(f"OK   {f.name:<40} {len(df):>5} rows  {time.time() - t0:.2f}s")
            if verbose:
                print(df.to_string(index=False), "\n")
    if failures:
        sys.exit(f"{len(failures)} SQL analysis file(s) failed: {failures}")
    print(f"\nAll {len(files)} SQL analyses ran; results in reports/sql_results/")


if __name__ == "__main__":
    main("--verbose" in sys.argv)
