"""
veli.store scraper — currently disabled.

veli.store is a JavaScript-heavy SPA whose search endpoint returns 404
for plain HTTP requests. It requires Playwright with Chromium, which is
incompatible with Python 3.14 on Windows (asyncio subprocess not implemented).

The scraper returns an empty list so the rest of the pipeline keeps working.
The start/stop_browser class methods are kept as no-ops so existing callers
don't break.
"""
import asyncio

from backend.scrapers.base_scraper import BaseScraper, GeorgianListing


class VeliStoreScraper(BaseScraper):
    platform = "veli"

    _browser = None
    _playwright = None

    @classmethod
    async def start_browser(cls):
        pass  # Playwright unavailable on Python 3.14

    @classmethod
    async def stop_browser(cls):
        pass

    async def search(self, query: str) -> list[GeorgianListing]:
        # veli.store requires Playwright which is unavailable
        return []
