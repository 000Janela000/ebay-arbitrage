"""
veli.store scraper using Playwright (shared Chromium browser instance).
veli.store is JavaScript-heavy and requires a real browser.
"""
import asyncio
import random
from typing import Optional

from backend.scrapers.base_scraper import BaseScraper, GeorgianListing
from backend.utils.price_parser import parse_gel_price

SEARCH_URL = "https://veli.store/search?q={query}"
BLOCKED_RESOURCES = {"image", "font", "media", "stylesheet"}


class VeliStoreScraper(BaseScraper):
    platform = "veli"

    _browser = None
    _playwright = None
    _lock = asyncio.Lock()

    @classmethod
    async def start_browser(cls):
        async with cls._lock:
            if cls._browser is not None:
                return
            try:
                from playwright.async_api import async_playwright
                cls._playwright = await async_playwright().start()
                cls._browser = await cls._playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                print("[veli] Playwright browser started")
            except Exception as e:
                print(f"[veli] Could not start Playwright: {e}")
                cls._browser = None

    @classmethod
    async def stop_browser(cls):
        async with cls._lock:
            if cls._browser:
                await cls._browser.close()
                cls._browser = None
            if cls._playwright:
                await cls._playwright.stop()
                cls._playwright = None

    async def search(self, query: str) -> list[GeorgianListing]:
        if self._browser is None:
            print("[veli] Browser not available, skipping")
            return []

        await asyncio.sleep(random.uniform(self.delay_min, self.delay_max))
        try:
            return await self._scrape(query)
        except Exception as e:
            print(f"[veli] Scrape failed for '{query}': {e}")
            return []

    async def _scrape(self, query: str) -> list[GeorgianListing]:
        context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="ka-GE",
        )
        page = await context.new_page()

        # Block heavy resources to speed up
        async def block_route(route):
            if route.request.resource_type in BLOCKED_RESOURCES:
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", block_route)

        try:
            url = SEARCH_URL.format(query=query.replace(" ", "+"))
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)

            # Wait for product cards
            try:
                await page.wait_for_selector(
                    '[data-testid="product-card"], [class*="ProductCard"], [class*="product-card"]',
                    timeout=8000,
                )
            except Exception:
                pass  # May not exist if no results

            # Extract listings via evaluate
            raw_items = await page.evaluate("""
                () => {
                    const selectors = [
                        '[data-testid="product-card"]',
                        '[class*="ProductCard"]',
                        '[class*="product-card"]',
                        '[class*="product_card"]',
                        'article',
                    ];
                    let cards = [];
                    for (const sel of selectors) {
                        const els = document.querySelectorAll(sel);
                        if (els.length > 0) { cards = Array.from(els); break; }
                    }
                    return cards.slice(0, 20).map(card => {
                        const titleEl = card.querySelector('h2, h3, [class*="title"], [class*="name"]');
                        const priceEl = card.querySelector('[class*="price"], [class*="Price"]');
                        const linkEl = card.querySelector('a[href]');
                        const imgEl = card.querySelector('img');
                        return {
                            title: titleEl ? titleEl.textContent.trim() : '',
                            price: priceEl ? priceEl.textContent.trim() : '',
                            url: linkEl ? linkEl.href : '',
                            image: imgEl ? (imgEl.src || imgEl.dataset.src || '') : '',
                        };
                    });
                }
            """)
        finally:
            await page.close()
            await context.close()

        listings = []
        for item in raw_items:
            title = item.get("title", "").strip()
            price_text = item.get("price", "").strip()
            if not title or not price_text:
                continue

            price_gel = parse_gel_price(price_text)
            if price_gel is None or price_gel <= 0:
                continue

            url = item.get("url", "")
            image_url: Optional[str] = item.get("image") or None

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
