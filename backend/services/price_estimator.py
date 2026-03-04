"""
Auction final price estimator using eBay BIN (Buy It Now) price distribution.
"""
import statistics
from typing import Optional

from backend.services.ebay_client import search_bin_prices

# G3: noise words stripped from title before building BIN query
_NOISE_WORDS = {
    'new', 'used', 'like', 'in', 'box', 'the', 'a', 'an', 'for', 'with', 'and', 'or',
    'of', 'to', 'by', 'from', 'lot', 'set', 'bundle', 'free', 'shipping', 'fast',
    'excellent', 'condition', 'great', 'good', 'very', 'nice', 'rare', 'beautiful',
    'vintage', 'authentic', 'genuine', 'original', 'oem', 'refurbished', 'open',
    'sealed', 'factory', 'unlocked', 'grade', 'certified', 'pre-owned', 'preowned',
    'brand', 'only', 'other', 'international', 'worldwide', 'priority', 'no',
}


def _build_bin_query(title: str) -> str:
    """
    G3: Extract meaningful terms from listing title, skipping noise/filler words.
    Takes up to 8 meaningful words — captures brand + model + key specs.
    """
    words = title.split()
    clean = [w for w in words if w.lower().rstrip('.,!') not in _NOISE_WORDS and len(w) > 1]
    return " ".join(clean[:8])


async def estimate_final_price(
    title: str,
    current_bid_usd: float,
    bid_count: int,
    category_id: Optional[str] = None,
) -> dict:
    """
    Estimate final auction price using BIN listings.
    Returns dict with: estimated_final_usd, confidence_score,
      bin_sample_count, bin_price_median_usd, bin_price_min_usd,
      bin_price_max_usd, estimation_method
    """
    # G3: smarter query — strip noise words, keep up to 8 meaningful terms
    query = _build_bin_query(title)

    bin_prices = await search_bin_prices(query, category_id=category_id, limit=20)

    # B6: outlier filter no longer anchored to current_bid (which can be $1 starting price).
    # Use absolute floor of $1 to drop garbage; apply upper cap only when bid is meaningful
    # so low-start auctions ($5) don't have valid $200 BIN prices wrongly excluded.
    bin_prices = [p for p in bin_prices if p >= 1.0]
    if current_bid_usd >= 10:
        bin_prices = [p for p in bin_prices if p < 10 * current_bid_usd]

    if len(bin_prices) >= 2:
        median_price = statistics.median(bin_prices)
        bid_factor = min(0.95, 0.65 + bid_count * 0.02)
        estimated = median_price * bid_factor
        confidence = min(0.95, 0.55 + len(bin_prices) * 0.05)
        method = "bin_median"
        result = {
            "bin_sample_count": len(bin_prices),
            "bin_price_median_usd": round(median_price, 2),
            "bin_price_min_usd": round(min(bin_prices), 2),
            "bin_price_max_usd": round(max(bin_prices), 2),
        }
    elif bid_count > 0:
        estimated = current_bid_usd * 1.15
        confidence = 0.35
        method = "current_bid_markup"
        result = {"bin_sample_count": 0, "bin_price_median_usd": None, "bin_price_min_usd": None, "bin_price_max_usd": None}
    else:
        estimated = current_bid_usd * 1.20
        confidence = 0.20
        method = "category_default"
        result = {"bin_sample_count": 0, "bin_price_median_usd": None, "bin_price_min_usd": None, "bin_price_max_usd": None}

    # Always enforce: estimated >= current_bid * 1.05
    min_estimate = current_bid_usd * 1.05
    estimated = max(estimated, min_estimate)

    return {
        "estimated_final_usd": round(estimated, 2),
        "confidence_score": round(confidence, 3),
        "estimation_method": method,
        **result,
    }
