"""
Abstract base scraper and GeorgianListing dataclass.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Optional


@dataclass
class GeorgianListing:
    platform: str
    title: str
    price_gel: float
    url: str
    image_url: Optional[str] = None
    similarity_score: float = 0.0
    low_confidence: bool = False
    price_mismatch: bool = False   # True when Georgian price > 5× eBay price (separate from similarity)
    view_count: Optional[int] = None
    order_count: Optional[int] = None


class BaseScraper(ABC):
    platform: str = ""
    delay_min: float = 1.0
    delay_max: float = 3.0

    @abstractmethod
    async def search(self, query: str) -> list[GeorgianListing]:
        """Search the platform for the given query and return listings."""
        ...

    @staticmethod
    def calc_similarity(query: str, title: str) -> float:
        """
        Title similarity: 0.6 × keyword_recall + 0.4 × sequence_ratio.
        Pure title-matching — never penalise for price.
        """
        query_words = set(query.lower().split())
        title_words = set(title.lower().split())

        if not query_words:
            return 0.0

        matching = query_words & title_words
        keyword_recall = len(matching) / len(query_words)
        seq_ratio = SequenceMatcher(None, query.lower(), title.lower()).ratio()

        return round(0.6 * keyword_recall + 0.4 * seq_ratio, 3)
