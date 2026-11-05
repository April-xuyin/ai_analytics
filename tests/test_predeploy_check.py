from scripts.predeploy_check import validate


def test_predeploy_validation_accepts_complete_configuration() -> None:
    values = {
        "DEEPSEEK_API_KEY": "d" * 32,
        "MAXCOMPUTE_ACCESS_ID": "id",
        "MAXCOMPUTE_ACCESS_KEY": "key",
        "MAXCOMPUTE_PROJECT": "project",
        "MAXCOMPUTE_ENDPOINT": "https://service.example.com/api",
        "API_AUTH_TOKEN": "a" * 32,
        "OPERATOR_API_TOKEN": "o" * 32,
        "OPERATOR_SHOPS": "shop-US",
        "QUERY_ENGINE": "maxcompute",
    }
    assert validate(values) == []


def test_predeploy_validation_rejects_unsafe_configuration() -> None:
    errors = validate({"QUERY_ENGINE": "local"})
    assert any("缺少配置" in item for item in errors)
    assert any("QUERY_ENGINE=maxcompute" in item for item in errors)
