"""Create the whitelisted MaxCompute tables from sql/maxcompute/ddl.sql."""

from __future__ import annotations

import os
from pathlib import Path

from odps import ODPS

PROJECT_DIR = Path(__file__).resolve().parents[1]


def load_env_file(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    load_env_file(PROJECT_DIR / ".env")
    ddl_path = PROJECT_DIR / "sql" / "maxcompute" / "ddl.sql"
    statements = [statement.strip() for statement in ddl_path.read_text(encoding="utf-8").split(";") if statement.strip()]

    client = ODPS(
        os.environ["MAXCOMPUTE_ACCESS_ID"],
        os.environ["MAXCOMPUTE_ACCESS_KEY"],
        os.environ["MAXCOMPUTE_PROJECT"],
        endpoint=os.environ["MAXCOMPUTE_ENDPOINT"],
    )

    print(f"Project: {client.project}")
    print(f"准备执行 {len(statements)} 条建表语句")
    for index, statement in enumerate(statements, start=1):
        table_name = statement.split()[5]
        print(f"[{index}/{len(statements)}] 创建 {table_name} ...", end=" ")
        instance = client.execute_sql(statement)
        instance.wait_for_success()
        print("成功")


if __name__ == "__main__":
    main()
