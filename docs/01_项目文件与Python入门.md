# 项目文件与 Python 入门

## 四个基础文件

### `.gitignore`

告诉 Git 哪些内容不要提交：`.venv/` 是虚拟环境，`.env` 可能含 API 密钥，`data/raw/` 和 `data/parquet/` 是真实数据，`*.duckdb` 是本地数据库，`__pycache__/` 和 `.pytest_cache/` 是运行缓存。

原则：提交代码、配置模板和文档；不提交密钥、真实数据和运行产物。

### `pyproject.toml`

Python 项目的配置文件，作用类似前端项目的 `package.json`。`name` 是项目名，`version` 是版本，`requires-python` 是最低 Python 版本，`dependencies` 是运行依赖：DuckDB 用于本地 SQL 查询，Pandas 用于数据处理，PyArrow 用于 CSV/Parquet 读写。`dev` 依赖中的 pytest 用于测试，ruff 用于代码检查。执行 `uv sync` 时，uv 会读取此文件并安装依赖。

### `README.md`

给人看的项目说明，通常包含项目用途、安装方式、运行命令、数据准备方式和目录说明。

### `scripts/convert_csv_to_parquet.py`

一个可重复运行的数据准备脚本：读取 CSV，清理 BOM、空列和 `\N`，再写出 Parquet。

## Python 语法速查

### 变量和类型

```python
name = "Cuspin"       # str 字符串
count = 10             # int 整数
rate = 0.25            # float 小数
enabled = True         # bool 布尔值
brands = ["A", "B"]   # list 列表
metric = {"name": "销售额", "field": "ordered_product_sales"}  # dict 字典
```

### 条件和循环

```python
if count > 0:
    print("有数据")

for brand in brands:
    print(brand)
```

Python 使用缩进表示代码块，通常使用 4 个空格。

### 函数

```python
def add(a: int, b: int) -> int:
    return a + b
```

`def` 定义函数；参数后的 `: int` 是类型注解；`-> int` 表示返回整数。

### 列表推导式

```python
squares = [value * value for value in [1, 2, 3]]
```

等价于：

```python
squares = []
for value in [1, 2, 3]:
    squares.append(value * value)
```

### 文件路径和模块

```python
from pathlib import Path
file_path = Path("data") / "sales.parquet"
```

`Path` 比手工拼接路径更安全。`import` 用于使用标准库或第三方库。

### 命令行参数和程序入口

执行 `python script.py /tmp/data` 时，`sys.argv[1]` 是 `/tmp/data`。

```python
if __name__ == "__main__":
    main()
```

直接运行文件时执行 `main()`；被其他文件导入时不自动执行。

## 学习重点

当前项目优先掌握：变量、列表/字典、条件、循环、函数、文件读写、异常处理、模块导入、JSON/YAML、虚拟环境和测试。AI 辅助开发的核心流程是：明确输入输出，让 AI 做小范围修改，自己运行测试，阅读报错，再按业务逻辑检查结果。

