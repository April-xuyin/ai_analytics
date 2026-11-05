from pathlib import Path

import yaml

from app.evaluation.query_plan_eval import evaluate_query_plans, summarize_query_plans
from app.metadata.loader import MetadataCatalog
from app.query.local_runner import LocalQueryRunner
from app.sql.generator import SafeSqlGenerator

PROJECT_DIR = Path(__file__).parents[1]


def test_query_plan_evaluation_suite_passes() -> None:
    with (PROJECT_DIR / "evals" / "query_plans.yaml").open(encoding="utf-8") as file:
        cases = yaml.safe_load(file)["cases"]
    results = evaluate_query_plans(
        SafeSqlGenerator(MetadataCatalog(PROJECT_DIR / "metadata")),
        cases,
        LocalQueryRunner(
            PROJECT_DIR / "data" / "parquet",
            PROJECT_DIR / "metadata" / "datasets.yaml",
        ),
    )
    assert summarize_query_plans(results) == {"total": 12, "passed": 12, "accuracy": 1.0}
