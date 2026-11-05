"""DeepSeek intent parser using its OpenAI-compatible API."""

from __future__ import annotations

import os

from openai import OpenAI

from app.intent.bailian import BailianConfigError, BailianIntentParser
from app.metadata.loader import MetadataCatalog


class DeepSeekIntentParser(BailianIntentParser):
    """Reuse the provider-neutral parsing protocol with DeepSeek settings."""

    def __init__(self, catalog: MetadataCatalog, client=None, model: str | None = None) -> None:
        if client is not None:
            super().__init__(catalog, client=client, model=model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
            return
        # DeepSeek 必须独立读取自己的配置，不能复用 BAILIAN_* 环境变量。
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key or api_key == "your_api_key_here":
            raise BailianConfigError("缺少有效的 DEEPSEEK_API_KEY，请检查 .env。")
        super().__init__(
            catalog,
            client=OpenAI(
                api_key=api_key,
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            ),
            model=model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        )
