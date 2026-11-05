"""AST-based read-only SQL policy shared by all query engines."""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from sqlglot import exp, parse
from sqlglot.errors import ParseError


class SqlSecurityError(ValueError):
    """Raised when SQL is malformed or outside the read-only policy."""


class SqlSecurityValidator:
    """Allow one query over whitelisted datasets and columns only."""

    BLOCKED_FUNCTIONS: ClassVar[set[str]] = {
        "READ_CSV", "READ_CSV_AUTO", "READ_JSON", "READ_JSON_AUTO",
        "READ_PARQUET", "READ_TEXT", "READ_BLOB", "READ_FILE",
        "PARQUET_SCAN", "CSV_SCAN", "HTTP_GET", "SHELL",
    }

    def __init__(
        self, datasets: Iterable[str], columns: Iterable[str] | None = None
    ) -> None:
        self.datasets = {name.lower() for name in datasets}
        self.columns = {name.lower() for name in columns or []}

    def validate(self, sql: str) -> None:
        statement = sql.strip().rstrip(";").strip()
        if not statement:
            raise SqlSecurityError("SQL 不能为空")
        try:
            trees = parse(statement, read="duckdb")
        except ParseError as exc:
            raise SqlSecurityError("SQL 语法无法安全解析") from exc
        if len(trees) != 1 or not isinstance(trees[0], exp.Query):
            raise SqlSecurityError("当前只允许执行单条 SELECT 或 WITH 查询")

        tree = trees[0]
        cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
        for table in tree.find_all(exp.Table):
            name = table.name.lower()
            if table.db or table.catalog:
                raise SqlSecurityError("禁止访问跨库、系统库或外部表")
            if name not in self.datasets and name not in cte_names:
                raise SqlSecurityError(f"数据集未加入白名单: {name or '表函数'}")

        for function in tree.find_all(exp.Func):
            function_name = (
                function.name if isinstance(function, exp.Anonymous) else function.sql_name()
            ).upper()
            if function_name in self.BLOCKED_FUNCTIONS or function_name.startswith("READ_"):
                raise SqlSecurityError(f"SQL 包含不允许的外部读取函数: {function_name}")

        if self.columns:
            derived_columns = {
                alias.alias.lower()
                for alias in tree.find_all(exp.Alias)
                if alias.alias
            }
            allowed_columns = self.columns | derived_columns
            for column in tree.find_all(exp.Column):
                if column.name != "*" and column.name.lower() not in allowed_columns:
                    raise SqlSecurityError(f"字段未加入白名单: {column.name}")
