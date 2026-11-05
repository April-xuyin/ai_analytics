# AI Analytics

Amazon US natural-language analytics assistant, built on the VG data warehouse.

## Project guide

项目目标、整体架构、实施阶段和当前进度见：

- [`docs/00_项目总览与实施路线.md`](docs/00_项目总览与实施路线.md)
- [`docs/01_项目文件与Python入门.md`](docs/01_项目文件与Python入门.md)
- [`docs/02_标准问题集说明.md`](docs/02_标准问题集说明.md)
- [`docs/03_问数服务与回答结构.md`](docs/03_问数服务与回答结构.md)
- [`docs/04_问题意图解析.md`](docs/04_问题意图解析.md)
- [`docs/05_问数链路图.html`](docs/05_问数链路图.html)
- [`docs/09_RAG与语义检索.md`](docs/09_RAG与语义检索.md)
- [`docs/10_安全与评测报告.md`](docs/10_安全与评测报告.md)
- [`docs/11_生产验收与运维手册.md`](docs/11_生产验收与运维手册.md)
- [`docs/12_项目复盘与简历材料.md`](docs/12_项目复盘与简历材料.md)

## Local data setup

Keep exported CSV files outside Git. From this directory, run:

```bash
uv sync
uv run python scripts/convert_csv_to_parquet.py "/Users/money/Downloads/ai项目/数据"
```

The cleaned Parquet files are written to `data/parquet/`.

## Local query layer

The first application module is `app/query/local_runner.py`. It provides a read-only DuckDB adapter over local Parquet files. Later, a MaxCompute adapter can implement the same interface without changing the upper-level question-answering flow.

Run tests with:

```bash
uv run pytest
```

## Start the local question-answering app

```bash
uv run python scripts/run_api.py
```

Then open `http://127.0.0.1:8000/` for the operator page, or
`http://127.0.0.1:8000/docs` for the API documentation.

## Start the production-like Docker stack

```bash
uv run python scripts/predeploy_check.py --env-file .env
docker compose up -d --build
```

Open `http://127.0.0.1:8080/`. Nginx is the public entry point; the FastAPI
container port is kept inside the Docker network.
