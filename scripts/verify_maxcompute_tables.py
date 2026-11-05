"""Verify that the six MaxCompute tables contain uploaded data."""

from __future__ import annotations

import os
from pathlib import Path

from odps import ODPS

PROJECT_DIR = Path(__file__).resolve().parents[1]
TABLES = [
    ("dws_brand_day_us", "stat_dt"),
    ("dws_sku_tag_day_us", "stat_dt"),
    ("ads_aws_sku_period_sales", "listing_date"),
    ("ads_aws_sku_recap_month_detail", "stat_month"),
    ("dwi_aws_sku_listing_date", "listing_date"),
    ("dim_north_star_target", "stat_month"),
]


def load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    load_env_file(PROJECT_DIR / ".env")
    client = ODPS(
        os.environ["MAXCOMPUTE_ACCESS_ID"],
        os.environ["MAXCOMPUTE_ACCESS_KEY"],
        os.environ["MAXCOMPUTE_PROJECT"],
        endpoint=os.environ["MAXCOMPUTE_ENDPOINT"],
    )
    for table_name, date_column in TABLES:
        sql = f"SELECT COUNT(*) AS row_count, MIN({date_column}) AS min_value, MAX({date_column}) AS max_value FROM {table_name}"
        instance = client.execute_sql(sql)
        instance.wait_for_success()
        with instance.open_reader(tunnel=True) as reader:
            row = next(iter(reader))
        print(f"{table_name}: rows={row[0]}, min_{date_column}={row[1]}, max_{date_column}={row[2]}")


if __name__ == "__main__":
    main()
