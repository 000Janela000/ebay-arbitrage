"""
Helpers for parsing Georgian price strings (GEL) which may use
various thousands separators and decimal formats.
"""
import re


def parse_gel_price(price_str: str) -> float | None:
    """
    Parse a GEL price string like:
      "1 299.00 ₾", "1,299", "1.299,00", "299₾", "299.00"
    Returns float or None if unparseable.
    """
    if not price_str:
        return None

    # Remove currency symbols and whitespace
    cleaned = re.sub(r"[₾GEL\s]", "", price_str.strip())

    # Detect format: if comma comes after dot, it's European format (1.299,00)
    if re.search(r"\d\.\d{3},\d{2}", cleaned):
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        # Remove space/comma thousands separators
        cleaned = re.sub(r"[\s,](?=\d{3})", "", cleaned)
        cleaned = cleaned.replace(",", ".")

    try:
        return float(cleaned)
    except ValueError:
        # Try extracting first number
        match = re.search(r"\d+(?:\.\d+)?", cleaned)
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass
        return None
