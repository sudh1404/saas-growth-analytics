"""Run a .sql file against the warehouse and print the result.  Usage: python scripts/run_query.py sql/01_funnel.sql"""
import sys
from pathlib import Path

import duckdb

DB = Path(__file__).resolve().parents[1] / "warehouse" / "saas.duckdb"
sql = Path(sys.argv[1]).read_text(encoding="utf-8")
with duckdb.connect(str(DB), read_only=True) as con:
    print(con.sql(sql).df().to_string(index=False))
