"""
mymarket.ge scraper using their JSON API via cloudscraper (bypasses Cloudflare).
"""
import asyncio
import random
from typing import Optional

import cloudscraper

from backend.scrapers.base_scraper import BaseScraper, GeorgianListing

API_URL = "https://api.mymarket.ge/api/en/products"
BASE_URL = "https://www.mymarket.ge"


class MymarketScraper(BaseScraper):
    platform = "mymarket"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._scraper = cloudscraper.create_scraper()

    async def search(self, query: str) -> list[GeorgianListing]:
        await asyncio.sleep(random.uniform(self.delay_min, self.delay_max))
        try:
            return await asyncio.to_thread(self._search_sync, query)
        except Exception as e:
            print(f"[mymarket] Request failed for '{query}': {e}")
            return []

    def _search_sync(self, query: str) -> list[GeorgianListing]:
        resp = self._scraper.post(
            API_URL,
            json={"keyword": query, "page": 1, "per_page": 20},
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        products = data.get("Prs", []) if isinstance(data, dict) else []

        listings = []
        for p in products[:20]:
            title = p.get("title", "").strip()
            price_raw = p.get("price", 0)
            currency_id = p.get("currency_id", 3)

            try:
                price_gel = float(price_raw)
            except (ValueError, TypeError):
                continue

            if price_gel <= 0:
                continue

            # currency_id 1 = USD, 3 = GEL — skip USD for now
            if currency_id == 1:
                continue

            seo_title = p.get("seo_title", "")
            url = f"{BASE_URL}{seo_title}" if seo_title else ""

            product_id = p.get("product_id", "")
            photo = p.get("photo", "")
            image_url: Optional[str] = None
            if product_id and photo:
                image_url = f"https://static.mymarket.ge/unsafe/rs:fit:250:0:0/plain/mymarket/photos/{photo}/{product_id}_1.webp?v={p.get('photo_ver', 0)}"

            similarity = self.calc_similarity(query, title)
            listings.append(GeorgianListing(
                platform=self.platform,
                title=title,
                price_gel=price_gel,
                url=url,
                image_url=image_url,
                similarity_score=similarity,
                low_confidence=similarity < 0.3,
            ))

        return sorted(listings, key=lambda x: x.similarity_score, reverse=True)
