from pathlib import Path

from app.metadata.loader import MetadataCatalog

METADATA_DIR = Path(__file__).parents[1] / "metadata"


def test_catalog_loads_metadata() -> None:
    catalog = MetadataCatalog(METADATA_DIR)
    assert len(catalog.datasets) == 6
    assert len(catalog.metrics) >= 8
    assert catalog.terms
    assert len(catalog.query_capabilities) == 2


def test_search_matches_sales_metric_and_dataset() -> None:
    catalog = MetadataCatalog(METADATA_DIR)
    result = catalog.search("最近30天各品牌销售额是多少")
    metric_names = {item["name"] for item in result["metrics"]}
    dataset_names = {item["name"] for item in result["datasets"]}
    assert "sales_amount" in metric_names
    assert "dws_brand_day_us" in dataset_names


def test_search_understands_sales_paraphrase() -> None:
    catalog = MetadataCatalog(METADATA_DIR)
    result = catalog.search("近一个月各品牌卖了多少钱")
    metric_names = {item["name"] for item in result["metrics"]}
    assert "sales_amount" in metric_names


def test_search_matches_business_term() -> None:
    catalog = MetadataCatalog(METADATA_DIR)
    result = catalog.search("哪些FBA SKU没有亚马逊主图")
    assert any(item["term"] == "AWS US" or item["term"] == "SKU" for item in result["terms"])


def test_catalog_checks_generic_query_capabilities() -> None:
    catalog = MetadataCatalog(METADATA_DIR)
    assert catalog.supports_query(["sales_amount"], ["shop_code"])
    assert not catalog.supports_query(["order_count"], ["shop_code"])
