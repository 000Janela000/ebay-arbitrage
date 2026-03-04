"""
zoomer.ge scraper: HTTPX + BeautifulSoup first, Playwright fallback.
"""
import asyncio
import random
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from backend.scrapers.base_scraper import BaseScraper, GeorgianListing
from backend.utils.price_parser import parse_gel_price

BASE_URL = "https://zoomer.ge"
SEARCH_URL = f"{BASE_URL}/search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ka-GE,ka;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class ZoomerScraper(BaseScraper):
    platform = "zoomer"

    async def search(self, query: str) -> list[GeorgianListing]:
        await asyncio.sleep(random.uniform(self.delay_min, self.delay_max))

        html = await self._fetch_httpx(query)
        if html:
            listings = self._parse(html, query)
            if listings:
                return listings

        # Playwright fallback
        return await self._playwright_fallback(query)

    async def _fetch_httpx(self, query: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as client:
                resp = await client.get(SEARCH_URL, params={"text": query})
                resp.raise_for_status()
                html = resp.text
                if len(html) < 500:  # Empty/minimal response
                    return None
                return html
        except Exception as e:
            print(f"[zoomer] HTTPX failed for '{query}': {e}")
            return None

    def _parse(self, html: str, query: str) -> list[GeorgianListing]:
        soup = BeautifulSoup(html, "lxml")
        listings = []

        items = (
            soup.select(".product-card")
            or soup.select(".product-item")
            or soup.select("[class*='product']")
            or soup.select("article")
        )

        if not items:
            print(f"[zoomer] No items parsed for '{query}', HTML length: {len(html)}")

        for item in items[:20]:
            title_el = (
                item.select_one("[class*='title']")
                or item.select_one("h3")
                or item.select_one("h2")
            )
            price_el = (
                item.select_one("[class*='price']")
                or item.select_one("[class*='Price']")
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

    async def _playwright_fallback(self, query: str) -> list[GeorgianListing]:
        try:
            from backend.scrapers.veli_store_scraper import VeliStoreScraper
            browser = VeliStoreScraper._browser
            if not browser:
                return []

            context = await browser.new_context(
                user_agent=HEADERS["User-Agent"],
                locale="ka-GE",
            )
            page = await context.new_page()
            try:
                url = f"{SEARCH_URL}?text={query.replace(' ', '+')}"
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                try:
                    await page.wait_for_selector("[class*='product']", timeout=6000)
                except Exception:
                    pass
                html = await page.content()
            finally:
                await page.close()
                await context.close()

            listings = self._parse(html, query)
            return listings
        except Exception as e:
            print(f"[zoomer] Playwright fallback failed for '{query}': {e}")
            return []
