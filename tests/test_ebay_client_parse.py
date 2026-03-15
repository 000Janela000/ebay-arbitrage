from backend.services.ebay_client import parse_auction_item


def test_parse_auction_item_prefers_current_bid_price():
    raw = {
        "itemId": "1",
        "categoryId": "261",
        "title": "Test",
        "currentBidPrice": {"value": "77.5", "currency": "USD"},
        "price": {"value": "10.0", "currency": "USD"},
        "bidCount": "4",
        "itemWebUrl": "https://example.com/1",
        "itemEndDate": "2026-03-07T12:00:00Z",
    }
    parsed = parse_auction_item(raw)
    assert parsed["current_bid_usd"] == 77.5
    assert parsed["bid_count"] == 4


def test_parse_auction_item_falls_back_to_price_and_categories_array():
    raw = {
        "itemId": "2",
        "categories": [{"categoryId": "999"}],
        "title": "Test 2",
        "price": {"value": "25.0", "currency": "USD"},
        "bidCount": 0,
        "itemHref": "https://example.com/2",
        "itemEndDate": "2026-03-07T12:00:00Z",
    }
    parsed = parse_auction_item(raw)
    assert parsed["current_bid_usd"] == 25.0
    assert parsed["ebay_category_id"] == "999"
    assert parsed["item_url"] == "https://example.com/2"
