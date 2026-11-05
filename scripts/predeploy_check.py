"""Validate production configuration without printing secret values."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_KEYS = {
    "DEEPSEEK_API_KEY",
    "MAXCOMPUTE_ACCESS_ID",
    "MAXCOMPUTE_ACCESS_KEY",
    "MAXCOMPUTE_PROJECT",
    "MAXCOMPUTE_ENDPOINT",
    "API_AUTH_TOKEN",
    "OPERATOR_API_TOKEN",
    "OPERATOR_SHOPS",
}


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def validate(values: dict[str, str]) -> list[str]:
    errors = [f"缺少配置: {key}" for key in sorted(REQUIRED_KEYS - values.keys())]
    for key in REQUIRED_KEYS & values.keys():
        if not values[key] or "your_" in values[key].lower() or "请" in values[key]:
            errors.append(f"配置未填写或仍是占位符: {key}")
    if values.get("QUERY_ENGINE", "").lower() != "maxcompute":
        errors.append("生产模拟必须设置 QUERY_ENGINE=maxcompute")
    if values.get("MAXCOMPUTE_ENDPOINT") and not values["MAXCOMPUTE_ENDPOINT"].startswith("https://"):
        errors.append("MAXCOMPUTE_ENDPOINT 必须使用 HTTPS")
    for key in ("API_AUTH_TOKEN", "OPERATOR_API_TOKEN"):
        if key in values and len(values[key]) < 32:
            errors.append(f"{key} 长度必须至少 32 位")
    if values.get("API_AUTH_TOKEN") == values.get("OPERATOR_API_TOKEN"):
        errors.append("管理员和运营令牌不能相同")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="部署前配置检查")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    if not args.env_file.is_file():
        raise SystemExit(f"找不到配置文件: {args.env_file}")
    errors = validate(load_env(args.env_file))
    print(json.dumps({"passed": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
