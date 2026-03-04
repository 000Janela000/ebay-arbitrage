"""
mymarket.ge scraper using HTTPX + BeautifulSoup.
"""
import asyncio
import random
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from backend.scrapers.base_scraper import BaseScraper, GeorgianListing
from backend.utils.price_parser import parse_gel_price

BASE_URL = "https://www.mymarket.ge"
SEARCH_URL = f"{BASE_URL}/search/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ka-GE,ka;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class MymarketScraper(BaseScraper):
    platform = "mymarket"

    async def search(self, query: str) -> list[GeorgianListing]:
        await asyncio.sleep(random.uniform(self.delay_min, self.delay_max))
        try:
            async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as client:
                resp = await client.get(SEARCH_URL, params={"query": query})
                resp.raise_for_status()
                html = resp.text
        except Exception as e:
            print(f"[mymarket] Request failed for '{query}': {e}")
            return []

        return self._parse(html, query)

    def _parse(self, html: str, query: str) -> list[GeorgianListing]:
        soup = BeautifulSoup(html, "lxml")
        listings = []

        # Try multiple possible selectors (site structure may vary)
        items = (
            soup.select(".product-item")
            or soup.select(".item-box")
            or soup.select("[data-id]")
            or soup.select(".card")
        )

        if not items:
            # Log for debugging
            print(f"[mymarket] No items found for '{query}', HTML length: {len(html)}")

        for item in items[:20]:
            title_el = (
                item.select_one(".product-title")
                or item.select_one(".title")
                or item.select_one("h3")
                or item.select_one("h2")
                or item.select_one("[class*='title']")
            )
            price_el = (
                item.select_one(".price")
                or item.select_one(".item-price")
                or item.select_one("[class*='price']")
            )
            link_el = item.select_one("a[href]")
            img_el = item.select_one("img")

            if not title_el or not price_el:
                continue

            title = title_el.get_text(strip=True)
            price_text = price_el.get_text(strip=True)
            price_gel = parse_gel_price(price_text)
            if price_gel is None or price_gel <= 0:
                continue

            url = ""
            if link_el:
                href = link_el.get("href", "")
                url = href if href.startswith("http") else f"{BASE_URL}{href}"

            image_url: Optional[str] = None
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src")

            similarity = self.calc_similarity(query, title)
            listing = GeorgianListing(
                platform=self.platform,
                title=title,
                price_gel=price_gel,
                url=url,
                image_url=image_url,
                similarity_score=similarity,
                low_confidence=similarity < 0.3,
            )
            listings.append(listing)

        return sorted(listings, key=lambda x: x.similarity_score, reverse=True)
