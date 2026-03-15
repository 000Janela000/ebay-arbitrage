"""
Orchestrates all Georgian scrapers in parallel and deduplicates results.
Returns scraper status alongside listings so the caller (and UI) can know
which platforms contributed data.
"""
import asyncio
import statistics
from typing import Optional

from backend.scrapers.base_scraper import GeorgianListing
from backend.scrapers.extra_scraper import ExtraScraper
from backend.scrapers.mymarket_scraper import MymarketScraper
from backend.scrapers.veli_store_scraper import VeliStoreScraper
from backend.scrapers.zoomer_scraper import ZoomerScraper
from backend.services.currency_service import get_usd_gel_rate


async def scrape_all_platforms(
    query: str,
    ebay_price_usd: float = 0.0,
    ebay_category_id: Optional[str] = None,
    mymarket_cat_ids: Optional[list[int]] = None,
    allowed_platforms: Optional[list[str]] = None,
) -> tuple[list[GeorgianListing], float, dict[str, bool]]:
    """
    Run all scrapers in parallel.

    mymarket_cat_ids takes precedence over ebay_category_id for mymarket filtering.
    If ebay_category_id is provided but mymarket_cat_ids is not, resolves via tree.

    Returns:
      listings       — deduplicated, sorted by similarity
      usd_gel_rate   — exchange rate used
      scraper_status — {platform: succeeded_bool}
    """
    usd_gel_rate = await get_usd_gel_rate()

    # Resolve mymarket categories if not provided directly
    resolved_cats = mymarket_cat_ids
    if resolved_cats is None and ebay_category_id:
        try:
            from backend.services.category_tree_service import resolve_mymarket_cats
            resolved_cats = await resolve_mymarket_cats(ebay_category_id)
        except Exception:
            resolved_cats = None

    try:
        results = await asyncio.wait_for(_run_all_scrapers(query, resolved_cats, allowed_platforms), timeout=30.0)
    except asyncio.TimeoutError:
        print(f"[orchestrator] Scrapers timed out (30s) for query: {query!r}")
        results = {}

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


async def _run_all_scrapers(
    query: str,
    mymarket_cat_ids: Optional[list[int]] = None,
    allowed_platforms: Optional[list[str]] = None,
) -> dict[str, tuple[bool, list[GeorgianListing]]]:
    scraper_map_all = {
        "mymarket": MymarketScraper(mymarket_cat_ids=mymarket_cat_ids),
        "extra": ExtraScraper(),
        "veli": VeliStoreScraper(),
        "zoomer": ZoomerScraper(),
    }

    # Skip scrapers that are explicitly disabled in the current runtime environment.
    scraper_map = {
        name: scraper for name, scraper in scraper_map_all.items()
        if getattr(scraper, "enabled", True)
    }
    if allowed_platforms is not None:
        allow = {p.lower() for p in allowed_platforms}
        scraper_map = {name: scraper for name, scraper in scraper_map.items() if name in allow}
    if not scraper_map:
        return {}

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
