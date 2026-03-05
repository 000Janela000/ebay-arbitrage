"""
extra.ge scraper using their Mercury search API via cloudscraper.

Two-step flow:
  1. POST mercury.extra.ge/search/ids  → get product IDs matching query
  2. POST mercury.extra.ge/offers/gimme → get full product details by IDs

Prices are in GEL.  Product URLs follow the pattern:
  https://extra.ge/product/{slug}/{secondaryId}
"""
import asyncio
import random
from typing import Optional

import cloudscraper

from backend.scrapers.base_scraper import BaseScraper, GeorgianListing

MERCURY_URL = "https://mercury.extra.ge"
BASE_URL = "https://extra.ge"

# How many product IDs to fetch per search, and how many details to resolve
SEARCH_LIMIT = 30
DETAIL_BATCH = 30


class ExtraScraper(BaseScraper):
    platform = "extra"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._scraper = cloudscraper.create_scraper()
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/",
        }

    async def search(self, query: str) -> list[GeorgianListing]:
        await asyncio.sleep(random.uniform(self.delay_min, self.delay_max))
        try:
            return await asyncio.to_thread(self._search_sync, query)
        except Exception as e:
            print(f"[extra] Request failed for '{query}': {e}")
            return []

    def _search_sync(self, query: str) -> list[GeorgianListing]:
        # Step 1: get product IDs
        ids = self._fetch_ids(query)
        if not ids:
            print(f"[extra] '{query}': 0 results")
            return []

        # Step 2: get product details
        products = self._fetch_details(ids[:DETAIL_BATCH])
        print(f"[extra] '{query}': {len(ids)} IDs → {len(products)} products")

        listings: list[GeorgianListing] = []
        for p in products:
            listing = self._parse_product(p, query)
            if listing:
                listings.append(listing)

        return sorted(listings, key=lambda x: x.similarity_score, reverse=True)

    def _fetch_ids(self, query: str) -> list[int]:
        try:
            resp = self._scraper.post(
                f"{MERCURY_URL}/search/ids",
                json={"searchText": query, "sortBy": 4, "pageSize": SEARCH_LIMIT},
                headers=self._headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("ids", [])
        except Exception as e:
            print(f"[extra] search/ids failed for '{query}': {e}")
            return []

    def _fetch_details(self, ids: list[int]) -> list[dict]:
        if not ids:
            return []
        try:
            resp = self._scraper.post(
                f"{MERCURY_URL}/offers/gimme",
                json={"ids": ids, "pageSize": len(ids)},
                headers=self._headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except Exception as e:
            print(f"[extra] offers/gimme failed: {e}")
            return []

    def _parse_product(self, p: dict, query: str) -> Optional[GeorgianListing]:
        title = p.get("productTitle", "").strip()
        if not title:
            return None

        price = p.get("discountPrice") or p.get("originalPrice")
        try:
            price_gel = float(price)
        except (ValueError, TypeError):
            return None
        if price_gel <= 0:
            return None

        slug = p.get("productSlug", "")
        secondary_id = p.get("secondaryId", "")
        url = f"{BASE_URL}/product/{slug}/{secondary_id}" if slug else ""

        image_url = p.get("productMainImageUrl")

        similarity = self._calc_similarity_with_title(query, title)

        return GeorgianListing(
            platform=self.platform,
            title=title,
            price_gel=price_gel,
            url=url,
            image_url=image_url,
            similarity_score=similarity,
            low_confidence=similarity < 0.2,
        )

    @staticmethod
    def _calc_similarity_with_title(query: str, title: str) -> float:
        """Keyword recall against product title."""
        query_words = set(query.lower().split())
        title_lower = title.lower()

        if not query_words:
            return 0.0

        matching = sum(1 for w in query_words if w in title_lower)
        return round(matching / len(query_words), 3)
