"""
mymarket.ge scraper using their JSON API via cloudscraper (bypasses Cloudflare).

Uses the Georgian (ka) API endpoint which returns richer titles and descriptions.
Similarity is computed against both title and description since mymarket titles
are often generic ("Mobile Phone Apple") while descriptions contain the real
model name ("iPhone 15 Pro 256GB").

Category filtering via CatID dramatically improves result relevance.
"""
import asyncio
import random
import re
from typing import Optional

import cloudscraper

from backend.scrapers.base_scraper import BaseScraper, GeorgianListing

API_URL = "https://api.mymarket.ge/api/ka/products"
BASE_URL = "https://www.mymarket.ge"

# Mapping from eBay category IDs to mymarket CatIDs.
# Some eBay categories map to multiple mymarket categories for broader coverage.
EBAY_TO_MYMARKET_CAT: dict[str, list[int]] = {
    "9355":   [69],              # Cell Phones → Mobile Phone
    "177":    [53],              # Laptops → Notebook
    "171485": [4517],            # Tablets → Tablet
    "139971": [164, 4553],       # Game Consoles → Gaming console + controllers
    "178893": [978],             # Smartwatches → Smart Watch
    "625":    [71],              # Cameras → Photo camera
    "293":    [999, 529, 82],    # Consumer Electronics → Electronics + Earphone + Speaker
    "11450":  [11],              # Clothing → Clothing and Accessories
    "11700":  [1066],            # Home & Garden → Home and garden
    "267":    [42],              # Books → Books
    "619":    [17],              # Musical Instruments → Music Instruments
    "220":    [65],              # Toys → Toys
}


class MymarketScraper(BaseScraper):
    platform = "mymarket"

    def __init__(self, mymarket_cat_ids: Optional[list[int]] = None, **kwargs):
        super().__init__(**kwargs)
        self._scraper = cloudscraper.create_scraper()
        self._cat_ids = mymarket_cat_ids

    async def search(self, query: str) -> list[GeorgianListing]:
        await asyncio.sleep(random.uniform(self.delay_min, self.delay_max))
        try:
            return await asyncio.to_thread(self._search_sync, query)
        except Exception as e:
            print(f"[mymarket] Request failed for '{query}': {e}")
            return []

    def _search_sync(self, query: str) -> list[GeorgianListing]:
        all_listings: list[GeorgianListing] = []

        # If we have category IDs, search each one separately for better results
        cat_ids = self._cat_ids or [None]
        for cat_id in cat_ids:
            payload: dict = {"keyword": query, "page": 1, "per_page": 30}
            if cat_id is not None:
                payload["CatID"] = cat_id

            try:
                resp = self._scraper.post(
                    API_URL,
                    json=payload,
                    headers={"Accept": "application/json", "Content-Type": "application/json"},
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                products = data.get("Prs", []) if isinstance(data, dict) else []
                cat_label = f" (CatID={cat_id})" if cat_id else ""
                print(f"[mymarket] '{query}'{cat_label}: {len(products)} raw results")

                for p in products[:30]:
                    listing = self._parse_product(p, query)
                    if listing:
                        all_listings.append(listing)
            except Exception as e:
                print(f"[mymarket] Error searching '{query}' CatID={cat_id}: {e}")

        return sorted(all_listings, key=lambda x: x.similarity_score, reverse=True)

    def _parse_product(self, p: dict, query: str) -> Optional[GeorgianListing]:
        title_ka = p.get("title", "").strip()
        descr = p.get("stripped_descr", "") or p.get("descr", "") or ""
        price_raw = p.get("price", 0)
        currency_id = p.get("currency_id", 3)

        try:
            price_gel = float(price_raw)
        except (ValueError, TypeError):
            return None

        if price_gel <= 0:
            return None

        # currency_id 1 = USD, 3 = GEL — skip USD listings
        if currency_id == 1:
            return None

        # Build a display title from the Georgian title + any model info in description
        display_title = title_ka
        latin_words = re.findall(r'[a-zA-Z0-9][a-zA-Z0-9\s./-]+', descr[:200])
        model_info = " ".join(latin_words).strip()
        if model_info and len(model_info) > 3:
            display_title = model_info[:80]

        seo_title = p.get("seo_title", "")
        url = f"{BASE_URL}{seo_title}" if seo_title else ""

        product_id = p.get("product_id", "")
        photo = p.get("photo", "")
        image_url: Optional[str] = None
        if product_id and photo:
            image_url = f"https://static.mymarket.ge/unsafe/rs:fit:250:0:0/plain/mymarket/photos/{photo}/{product_id}_1.webp?v={p.get('photo_ver', 0)}"

        # Compute similarity against both title and description
        combined_text = f"{title_ka} {descr[:200]}"
        similarity = self._calc_similarity_with_description(query, combined_text)

        return GeorgianListing(
            platform=self.platform,
            title=display_title,
            price_gel=price_gel,
            url=url,
            image_url=image_url,
            similarity_score=similarity,
            low_confidence=similarity < 0.2,
        )

    @staticmethod
    def _calc_similarity_with_description(query: str, text: str) -> float:
        """Keyword recall against a combined title+description text."""
        query_words = set(query.lower().split())
        text_lower = text.lower()

        if not query_words:
            return 0.0

        matching = sum(1 for w in query_words if w in text_lower)
        keyword_recall = matching / len(query_words)

        return round(keyword_recall, 3)
