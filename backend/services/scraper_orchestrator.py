"""
Orchestrates all Georgian scrapers in parallel and deduplicates results.
Returns scraper status alongside listings so the caller (and UI) can know
which platforms contributed data.
"""
import asyncio
import statistics
from typing import Optional

from backend.scrapers.base_scraper import GeorgianListing
from backend.scrapers.mymarket_scraper import MymarketScraper, EBAY_TO_MYMARKET_CAT
from backend.scrapers.veli_store_scraper import VeliStoreScraper
from backend.scrapers.zoomer_scraper import ZoomerScraper
from backend.services.currency_service import get_usd_gel_rate


async def scrape_all_platforms(
    query: str,
    ebay_price_usd: float = 0.0,
    ebay_category_id: Optional[str] = None,
) -> tuple[list[GeorgianListing], float, dict[str, bool]]:
    """
    Run all scrapers in parallel.
    Returns:
      listings       — deduplicated, sorted by similarity
      usd_gel_rate   — exchange rate used
      scraper_status — {platform: succeeded_bool}
    """
    # B5: run scrapers with a hard timeout to prevent refresh jobs hanging indefinitely
    usd_gel_rate = await get_usd_gel_rate()
    try:
        results = await asyncio.wait_for(_run_all_scrapers(query, ebay_category_id), timeout=30.0)
    except asyncio.TimeoutError:
        print(f"[orchestrator] Scrapers timed out (30s) for query: {query!r}")
        results = {"mymarket": (False, []), "veli": (False, []), "zoomer": (False, [])}

    scraper_status: dict[str, bool] = {}
    all_listings: list[GeorgianListing] = []

    for platform, (ok, listings) in results.items():
        scraper_status[platform] = ok
        for listing in listings:
            if ebay_price_usd > 0:
                listing = _apply_price_sanity(listing, ebay_price_usd, usd_gel_rate)
            all_listings.append(listing)

    # Deduplicate by (platform, url) — ignore blanks
    seen: set[tuple[str, str]] = set()
    deduped: list[GeorgianListing] = []
    for listing in all_listings:
        key = (listing.platform, listing.url)
        if listing.url and key not in seen:
            seen.add(key)
            deduped.append(listing)

    deduped.sort(key=lambda x: x.similarity_score, reverse=True)
    return deduped, usd_gel_rate, scraper_status


async def _run_all_scrapers(query: str, ebay_category_id: Optional[str] = None) -> dict[str, tuple[bool, list[GeorgianListing]]]:
    mymarket_cats = EBAY_TO_MYMARKET_CAT.get(ebay_category_id) if ebay_category_id else None
    scraper_map = {
        "mymarket": MymarketScraper(mymarket_cat_ids=mymarket_cats),
        "veli": VeliStoreScraper(),
        "zoomer": ZoomerScraper(),
    }
    tasks = {name: scraper.search(query) for name, scraper in scraper_map.items()}
    raw = await asyncio.gather(*tasks.values(), return_exceptions=True)

    out: dict[str, tuple[bool, list[GeorgianListing]]] = {}
    for name, result in zip(tasks.keys(), raw):
        if isinstance(result, Exception):
            print(f"[orchestrator] Scraper '{name}' failed: {result}")
            out[name] = (False, [])
        else:
            out[name] = (True, result)
    return out


def _apply_price_sanity(
    listing: GeorgianListing,
    ebay_price_usd: float,
    usd_gel_rate: float,
) -> GeorgianListing:
    """
    Flag price mismatches WITHOUT touching similarity_score.
    similarity_score = pure title match quality (never penalised for price)
    price_mismatch   = separate flag for ">5× eBay price" anomaly
    """
    if usd_gel_rate <= 0:
        return listing
    georgian_usd = listing.price_gel / usd_gel_rate
    if ebay_price_usd > 0 and georgian_usd > 5 * ebay_price_usd:
        listing.price_mismatch = True
        listing.low_confidence = True
    return listing


def calc_median_price_gel(listings: list[GeorgianListing]) -> Optional[float]:
    prices = [l.price_gel for l in listings if l.price_gel > 0]
    return statistics.median(prices) if prices else None
