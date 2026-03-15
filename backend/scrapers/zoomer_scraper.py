"""
zoomer.ge scraper — currently disabled.

zoomer.ge has a broken SSL certificate (hostname mismatch) and is a fully
client-side rendered Next.js SPA with no discoverable public API.
Without Playwright (incompatible with Python 3.14 on Windows) there is
no reliable way to scrape it.

The scraper returns an empty list so the rest of the pipeline keeps working.
"""
import asyncio
import random

from backend.scrapers.base_scraper import BaseScraper, GeorgianListing


class ZoomerScraper(BaseScraper):
    platform = "zoomer"
    enabled = False

    async def search(self, query: str) -> list[GeorgianListing]:
        # zoomer.ge SSL cert is broken + fully client-side SPA
        return []
