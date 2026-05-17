"""
Amazon 关键词获取器 — 使用 Amazon 免费搜索自动补全 API 获取真实热词。

无需 API Key，无需浏览器。Amazon 公开接口:
  https://completion.amazon.com/api/2017/suggestions

返回真实买家搜索的高频词，按搜索量排名。
"""

import asyncio
import re
from typing import Optional

import httpx


class AmazonKeywordFetcher:
    """通过 Amazon Autocomplete API 获取真实搜索热词"""

    AUTOCOMPLETE_URL = "https://completion.amazon.com/api/2017/suggestions"
    MID = "ATVPDKIKX0DER"  # Amazon US
    ALIAS = "aps"

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15)
        return self._client

    async def fetch(self, prefix: str, max_results: int = 10) -> list[dict]:
        """
        获取单个前缀的自动补全建议。

        返回: [{"keyword": "bluetooth headphones", "rank": 1}, ...]
        """
        try:
            resp = await self.client.get(
                self.AUTOCOMPLETE_URL,
                params={
                    "mid": self.MID,
                    "alias": self.ALIAS,
                    "prefix": prefix.strip(),
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                suggestions = data.get("suggestions", [])
                results = []
                for i, s in enumerate(suggestions):
                    kw = s.get("value", "").strip().lower()
                    if kw:
                        results.append({
                            "keyword": kw,
                            "rank": i + 1,
                            "source": "amazon_autocomplete",
                        })
                return results[:max_results]
        except Exception:
            pass
        return []

    async def fetch_deep(self, seed: str, max_results: int = 30,
                          translate_fn=None) -> list[dict]:
        """
        深度挖掘：从种子词派生出多个变体前缀，聚合所有建议。

        自动检测中文输入并翻译为英文（Amazon US 只支持英文搜索）。

        策略:
          1. 检测语言 → 中文则翻译为英文
          2. 搜索 seed 本身
          3. 搜索 "best seed"
          4. 搜索 "seed for"
          5. 追加 common modifier 前缀
        """
        # 语言检测：含 CJK 字符则翻译
        original_seed = seed
        if self._is_cjk(seed) and translate_fn:
            translated = await translate_fn(seed)
            if translated and translated != seed:
                seed = translated

        variants = [
            seed,
            f"best {seed}",
            f"{seed} for",
        ]

        # 追加 common modifier 前缀
        for mod in ["wireless ", "bluetooth ", "professional ", "premium ",
                     "portable ", "mini ", "kids "]:
            variants.append(f"{mod}{seed}")

        all_kws = {}
        tasks = [self.fetch(v) for v in variants]
        results = await asyncio.gather(*tasks)

        for suggestions in results:
            for s in suggestions:
                kw = s["keyword"]
                if kw not in all_kws:
                    all_kws[kw] = s

        # 按 rank 排序，去重
        sorted_kws = sorted(all_kws.values(), key=lambda x: x["rank"])
        return sorted_kws[:max_results]

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _is_cjk(text: str) -> bool:
        """检测是否包含中日韩字符"""
        for ch in text:
            cp = ord(ch)
            if (0x4E00 <= cp <= 0x9FFF or   # CJK Unified
                0x3400 <= cp <= 0x4DBF or   # CJK Extension A
                0x3040 <= cp <= 0x309F or   # Hiragana
                0x30A0 <= cp <= 0x30FF or   # Katakana
                0xAC00 <= cp <= 0xD7AF):    # Hangul
                return True
        return False


# 全局单例
_fetcher: Optional[AmazonKeywordFetcher] = None


def get_fetcher() -> AmazonKeywordFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = AmazonKeywordFetcher()
    return _fetcher
