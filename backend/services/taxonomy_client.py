"""
eBay Taxonomy API client for fetching category trees.
Uses the same OAuth credentials as the Browse API.
"""
from typing import Any

import httpx

from backend.services.ebay_client import EbayTokenManager, _get_credentials, _track_api_call


# US marketplace category tree ID
US_CATEGORY_TREE_ID = "0"


async def fetch_category_tree() -> dict[str, Any]:
    """
    Fetch the full US eBay category tree.
    Returns the raw API response with nested categoryTreeNodes.
    """
    client_id, client_secret, base_url = await _get_credentials()
    if not client_id:
        raise ValueError("eBay API credentials not configured")

    token = await EbayTokenManager.get_token(client_id, client_secret, base_url)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{base_url}/commerce/taxonomy/v1/category_tree/{US_CATEGORY_TREE_ID}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=60,  # Full tree can be large
        )
        resp.raise_for_status()

    await _track_api_call(1)
    return resp.json()


async def fetch_category_subtree(category_id: str) -> dict[str, Any]:
    """
    Fetch a subtree starting from a specific category.
    Useful for lazy-loading if the full tree is too large.
    """
    client_id, client_secret, base_url = await _get_credentials()
    if not client_id:
        raise ValueError("eBay API credentials not configured")

    token = await EbayTokenManager.get_token(client_id, client_secret, base_url)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{base_url}/commerce/taxonomy/v1/category_tree/{US_CATEGORY_TREE_ID}/get_category_subtree",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            params={"category_id": category_id},
            timeout=30,
        )
        resp.raise_for_status()

    await _track_api_call(1)
    return resp.json()
