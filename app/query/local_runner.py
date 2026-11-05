"""Execute read-only SQL against the local Parquet data with DuckDB."""

from __future__ import annotations

import re
from pathlib import Path

import duckdb
import yaml

from app.query.sql_security import SqlSecurityError, SqlSecurityValidator


class QueryError(ValueError):
    """Raised when a query is not allowed or cannot be executed."""


class LocalQueryRunner:
    """Small query adapter that can later be replaced by a MaxCompute adapter."""

    def __init__(
        self,
        data_dir: str | Path = "data/parquet",
        metadata_file: str | Path = "metadata/datasets.yaml",
    ) -> None:
        self.data_dir = Path(data_dir)
        self.metadata_file = Path(metadata_file)
        self.datasets = self._load_dataset_names()
        self.columns = self._load_column_names()

    def _load_dataset_names(self) -> set[str]:
        """Load the queryable dataset whitelist from YAML metadata."""
        if not self.metadata_file.is_file():
            raise QueryError(f"找不到数据集元数据: {self.metadata_file}")
        text = self.metadata_file.read_text(encoding="utf-8")
        # 当前只需要提取 `- name: xxx`；完整 YAML 读取会在元数据模块实现。
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

    def parquet_path(self, dataset: str) -> Path:
        """Resolve a dataset name from the whitelist to a local Parquet file."""
        if not re.fullmatch(r"[A-Za-z0-9_]+", dataset):
            raise QueryError("数据集名称格式不合法")
        if dataset not in self.datasets:
            raise QueryError(f"数据集未加入白名单: {dataset}")
        path = self.data_dir / f"{dataset}.parquet"
        if not path.is_file():
            raise QueryError(f"找不到数据集: {dataset}")
        return path

    def execute(self, sql: str, max_rows: int = 1000) -> list[dict[str, object]]:
        """Execute one read-only statement and return rows as dictionaries."""
        statement = sql.strip().rstrip(";").strip()
        if not statement:
            raise QueryError("SQL 不能为空")
        if max_rows < 1:
            raise QueryError("max_rows 必须大于 0")
        try:
            SqlSecurityValidator(self.datasets, self.columns).validate(statement)
        except SqlSecurityError as exc:
            raise QueryError(str(exc)) from exc

        wrapped_sql = f"SELECT * FROM ({statement}) AS result LIMIT {int(max_rows)}"
        try:
            with duckdb.connect() as connection:
                self._register_dataset_views(connection)
                cursor = connection.execute(wrapped_sql)
                columns = [item[0] for item in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except duckdb.Error as exc:
            raise QueryError(f"SQL 执行失败: {exc}") from exc

    def _register_dataset_views(self, connection: duckdb.DuckDBPyConnection) -> None:
        """Expose whitelisted Parquet files as SQL views using dataset names."""
        for dataset in self.datasets:
            path = self.parquet_path(dataset).resolve().as_posix().replace("'", "''")
            connection.execute(
                f'''CREATE TEMP VIEW "{dataset}" AS
                    SELECT * FROM read_parquet('{path}')'''
            )
