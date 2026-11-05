from pathlib import Path

import yaml

from app.intent.parser import RuleBasedIntentParser
from app.metadata.loader import MetadataCatalog


def test_all_supported_question_metrics_are_recognized() -> None:
    root = Path(__file__).parents[1]
    with (root / "evals" / "questions.yaml").open(encoding="utf-8") as file:
        questions = yaml.safe_load(file)["questions"]
    parser = RuleBasedIntentParser(MetadataCatalog(root / "metadata"))
    checked = 0
    for item in questions:
        if item.get("status") != "implemented" or not item.get("expected_metrics"):
            continue
        intent = parser.parse(item["question"])
        checked += 1
        assert intent.metric in item["expected_metrics"], item["id"]
    # 规则解析器只是基线；完整覆盖由 DeepSeek 评测负责。
    assert checked >= 1
