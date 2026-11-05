"""Convert exported MaxCompute CSV files into clean, typed Parquet files."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pyarrow.csv as pacsv
import pyarrow.parquet as pq


def clean_name(name: str, index: int) -> str:
    # 导出文件可能带 UTF-8 BOM 或空表头，先统一清理。
    name = name.lstrip("\ufeff").strip()
    return name or f"_unnamed_{index}"


def clean_csv(source: Path, target: Path) -> int:
    # 逐行清洗 CSV，避免覆盖原始文件。
    with source.open("r", encoding="utf-8-sig", newline="") as src, target.open(
        "w", encoding="utf-8", newline=""
    ) as out:
        reader = csv.reader(src)
        writer = csv.writer(out, lineterminator="\n")
        header = next(reader)  # 第一行是字段名
        names = [clean_name(value, i) for i, value in enumerate(header)]
        keep = [i for i, value in enumerate(names) if not value.startswith("_unnamed_")]
        writer.writerow([names[i] for i in keep])
        rows = 0
        for row in reader:  # 逐行处理数据
            if not row:
                continue
            row += [""] * (len(names) - len(row))
            writer.writerow(["" if row[i] == r"\N" else row[i] for i in keep])
            rows += 1
    return rows


def main() -> None:
    # 入口负责参数校验、遍历文件和调用转换逻辑。
    if len(sys.argv) != 2:
        raise SystemExit("用法: uv run python scripts/convert_csv_to_parquet.py <CSV目录>")
    source_dir = Path(sys.argv[1]).expanduser().resolve()
    output_dir = Path("data/parquet")
    staging_dir = Path("data/.cleaned")
    output_dir.mkdir(parents=True, exist_ok=True)
    staging_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted(source_dir.glob("*.csv")):
        cleaned = staging_dir / source.name
        rows = clean_csv(source, cleaned)
        # 清洗后的 CSV 再交给 Arrow 推断类型并读入内存。
        table = pacsv.read_csv(
            cleaned,
            read_options=pacsv.ReadOptions(autogenerate_column_names=False),
            convert_options=pacsv.ConvertOptions(null_values=[""], strings_can_be_null=True),
        )
        target = output_dir / f"{source.stem}.parquet"
        # Parquet 是列式格式，适合后续用 DuckDB 查询。
        pq.write_table(table, target, compression="zstd")
        print(f"{source.name}: {rows:,} rows -> {target}")


if __name__ == "__main__":
    main()
