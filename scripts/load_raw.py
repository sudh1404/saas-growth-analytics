"""Load every CSV in data/raw into the DuckDB warehouse under the `raw` schema."""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = ROOT / "warehouse" / "saas.duckdb"


def main():
    DB.parent.mkdir(exist_ok=True)
    con = duckdb.connect(str(DB))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    for csv in sorted(RAW.glob("*.csv")):
        table = csv.stem
        con.execute(f"""
            CREATE OR REPLACE TABLE raw.{table} AS
            SELECT *, current_timestamp AS _loaded_at
            FROM read_csv_auto('{csv.as_posix()}', header = true)
        """)
        n = con.execute(f"SELECT count(*) FROM raw.{table}").fetchone()[0]
        print(f"raw.{table:<16} {n:>8,} rows")
    con.close()


if __name__ == "__main__":
    main()
