"""Read-only MaxCompute query adapter."""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from odps import ODPS

from app.query.local_runner import QueryError
from app.query.sql_security import SqlSecurityError, SqlSecurityValidator


class MaxComputeQueryRunner:
    """Execute whitelisted analytics SQL against a MaxCompute project."""

    def __init__(self, metadata_file: str | Path = "metadata/datasets.yaml") -> None:
        self.metadata_file = Path(metadata_file)
        self.datasets = self._load_dataset_names()
        self.columns = self._load_column_names()
        self.timeout_seconds = int(os.getenv("MAXCOMPUTE_QUERY_TIMEOUT_SECONDS", "60"))
        self.client = ODPS(
            os.environ["MAXCOMPUTE_ACCESS_ID"],
            os.environ["MAXCOMPUTE_ACCESS_KEY"],
            os.environ["MAXCOMPUTE_PROJECT"],
            endpoint=os.environ["MAXCOMPUTE_ENDPOINT"],
        )

    def _load_dataset_names(self) -> set[str]:
        if not self.metadata_file.is_file():
            raise QueryError(f"找不到数据集元数据: {self.metadata_file}")
        text = self.metadata_file.read_text(encoding="utf-8")
        names = set(re.findall(r"(?m)^\s*-\s+name:\s*([A-Za-z0-9_]+)\s*$", text))
        if not names:
            raise QueryError("数据集白名单为空")
        return names

    def _load_column_names(self) -> set[str]:
        document = yaml.safe_load(self.metadata_file.read_text(encoding="utf-8")) or {}
        return {
            str(column)
            for dataset in document.get("datasets", [])
            for column in [
                dataset.get("time_field"),
                *dataset.get("dimensions", []),
                *dataset.get("metrics", []),
            ]
            if column
        }

    def execute(self, sql: str, max_rows: int = 1000) -> list[dict[str, object]]:
        statement = sql.strip().rstrip(";").strip()
        if not statement:
            raise QueryError("SQL 不能为空")
        try:
            SqlSecurityValidator(
                self.datasets, getattr(self, "columns", None)
            ).validate(statement)
        except SqlSecurityError as exc:
            raise QueryError(str(exc)) from exc
        if max_rows < 1:
            raise QueryError("max_rows 必须大于 0")
        statement = self._to_maxcompute_sql(statement)
        try:
            instance = self.client.execute_sql(statement)
            instance.wait_for_success(timeout=self.timeout_seconds)
            with instance.open_reader(tunnel=True) as reader:
                columns = [column.name for column in reader.schema.columns]
                return [
                    {column: row[column] for column in columns}
                    for index, row in enumerate(reader)
                    if index < max_rows
                ]
        except Exception as exc:
            raise QueryError(f"MaxCompute SQL 执行失败: {exc}") from exc

    @staticmethod
    def _to_maxcompute_sql(statement: str) -> str:
        """Translate the small, known DuckDB dialect subset used by templates."""
        converted = re.sub(r"TRY_CAST\(([^()]+) AS ([A-Za-z]+)\)", r"CAST(\1 AS \2)", statement, flags=re.IGNORECASE)
        converted = re.sub(
            r"MAX\(stat_dt\)\s*-\s*INTERVAL\s+(\d+)\s+DAY",
            r"DATEADD(MAX(stat_dt), -\1, 'dd')",
            converted,
            flags=re.IGNORECASE,
        )
        converted = re.sub(
            r"MAX\(stat_dt\)\s*-\s*INTERVAL\s+(\d+)\s+MONTH",
            r"DATEADD(MAX(stat_dt), -\1, 'mm')",
            converted,
            flags=re.IGNORECASE,
        )
        # The SKU daily table already has one brand per SKU in this query;
        # MaxCompute does not support MAX over STRING, so group the brand.
        if "MAX(brand) AS brand" in converted:
            converted = converted.replace("MAX(brand) AS brand", "brand AS brand")
            converted = converted.replace(
                "GROUP BY seller_sku, asin", "GROUP BY seller_sku, asin, brand"
            )
        return converted
