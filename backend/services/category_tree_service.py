"""
Service layer for the eBay category tree.
Handles syncing from the Taxonomy API, tree traversal, and inheritance resolution.
"""
import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.models import EbayCategory, CategoryTreeMeta, Category
from backend.services.taxonomy_client import fetch_category_tree

# Old hardcoded mappings — used during migration to seed known categories
_LEGACY_MYMARKET_MAP: dict[str, list[int]] = {
    "9355":   [69],
    "177":    [53],
    "171485": [4517],
    "139971": [164, 4553],
    "178893": [978],
    "625":    [71],
    "293":    [999, 529, 82],
    "11450":  [11],
    "11700":  [1066],
    "267":    [42],
    "619":    [17],
    "220":    [65],
}

_LEGACY_WEIGHTS: dict[str, float] = {
    "9355": 0.2,
    "177": 2.0,
    "171485": 0.6,
    "139971": 0.5,
    "178893": 0.1,
    "625": 0.8,
    "293": 1.0,
    "11450": 0.4,
    "11700": 1.5,
    "267": 0.3,
    "619": 3.0,
    "220": 0.8,
}


async def sync_category_tree() -> int:
    """
    Fetch the full eBay category tree and upsert all nodes into the DB.
    Returns the total number of categories synced.
    """
    print("[category_tree] Fetching category tree from eBay Taxonomy API...")
    tree_data = await fetch_category_tree()

    tree_version = tree_data.get("categoryTreeVersion", "unknown")
    root_node = tree_data.get("rootCategoryNode", {})

    # Flatten the tree into a list of rows
    rows: list[dict] = []
    _flatten_tree(root_node, parent_id=None, level=0, rows=rows)

    print(f"[category_tree] Parsed {len(rows)} categories (version {tree_version})")

    # Upsert all into DB
    async with AsyncSessionLocal() as db:
        for row in rows:
            result = await db.execute(
                select(EbayCategory).where(
                    EbayCategory.ebay_category_id == row["ebay_category_id"]
                )
            )
            existing = result.scalar_one_or_none()
            if existing is None:
                cat = EbayCategory(**row)
                # Apply legacy mappings for known categories
                cat_id = row["ebay_category_id"]
                if cat_id in _LEGACY_MYMARKET_MAP:
                    cat.mymarket_cat_ids = json.dumps(_LEGACY_MYMARKET_MAP[cat_id])
                    cat.is_tracked = True
                if cat_id in _LEGACY_WEIGHTS:
                    cat.default_weight_kg = _LEGACY_WEIGHTS[cat_id]
                db.add(cat)
            else:
                # Update tree structure but preserve user data
                existing.name = row["name"]
                existing.parent_id = row["parent_id"]
                existing.level = row["level"]
                existing.is_leaf = row["is_leaf"]

        # Update metadata
        meta_result = await db.execute(select(CategoryTreeMeta).where(CategoryTreeMeta.id == 1))
        meta = meta_result.scalar_one_or_none()
        if meta is None:
            meta = CategoryTreeMeta(id=1)
            db.add(meta)
        meta.tree_version = tree_version
        meta.last_fetched_at = datetime.utcnow()
        meta.total_categories = len(rows)

        await db.commit()

    print(f"[category_tree] Synced {len(rows)} categories to DB")
    return len(rows)


def _flatten_tree(
    node: dict[str, Any],
    parent_id: Optional[str],
    level: int,
    rows: list[dict],
):
    """Recursively flatten the eBay category tree into a flat list."""
    category = node.get("category", {})
    cat_id = str(category.get("categoryId", ""))
    cat_name = category.get("categoryName", "")

    if not cat_id:
        return

    is_leaf = node.get("leafCategoryTreeNode", False)

    rows.append({
        "ebay_category_id": cat_id,
        "name": cat_name,
        "parent_id": parent_id,
        "level": level,
        "is_leaf": is_leaf,
    })

    for child in node.get("childCategoryTreeNodes", []):
        _flatten_tree(child, parent_id=cat_id, level=level + 1, rows=rows)


async def migrate_legacy_categories():
    """
    Copy analysis data from old Category table to EbayCategory table
    for any matching category IDs.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Category))
        old_cats = result.scalars().all()

        for old in old_cats:
            res = await db.execute(
                select(EbayCategory).where(
                    EbayCategory.ebay_category_id == old.ebay_category_id
                )
            )
            new_cat = res.scalar_one_or_none()
            if new_cat is None:
                continue

            # Copy analysis data
            if old.avg_ebay_sold_usd is not None:
                new_cat.avg_ebay_sold_usd = old.avg_ebay_sold_usd
            if old.avg_georgian_price_usd is not None:
                new_cat.avg_georgian_price_usd = old.avg_georgian_price_usd
            if old.avg_profit_margin_pct is not None:
                new_cat.avg_profit_margin_pct = old.avg_profit_margin_pct
            if old.avg_weight_kg is not None:
                new_cat.avg_weight_kg = old.avg_weight_kg
            if old.total_active_auctions:
                new_cat.total_active_auctions = old.total_active_auctions
            if old.last_analyzed_at:
                new_cat.last_analyzed_at = old.last_analyzed_at

            new_cat.is_tracked = True

        await db.commit()

    print("[category_tree] Migrated legacy category analysis data")


async def is_tree_populated() -> bool:
    """Check if the category tree has been fetched."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CategoryTreeMeta).where(CategoryTreeMeta.id == 1))
        meta = result.scalar_one_or_none()
        return meta is not None and meta.total_categories is not None and meta.total_categories > 0


async def get_children(parent_id: Optional[str]) -> list[EbayCategory]:
    """Get immediate children of a category. Pass None for root-level categories."""
    async with AsyncSessionLocal() as db:
        if parent_id is None:
            # Root level = level 1 (children of the "Root" node which is level 0)
            q = select(EbayCategory).where(EbayCategory.level == 1).order_by(EbayCategory.name)
        else:
            q = select(EbayCategory).where(EbayCategory.parent_id == parent_id).order_by(EbayCategory.name)
        result = await db.execute(q)
        return list(result.scalars().all())


async def get_child_counts(parent_id: Optional[str]) -> dict[str, int]:
    """Get child counts for all children of a parent."""
    async with AsyncSessionLocal() as db:
        if parent_id is None:
            children_q = select(EbayCategory.ebay_category_id).where(EbayCategory.level == 1)
        else:
            children_q = select(EbayCategory.ebay_category_id).where(EbayCategory.parent_id == parent_id)

        child_result = await db.execute(children_q)
        child_ids = [r[0] for r in child_result.all()]

        if not child_ids:
            return {}

        # Count grandchildren for each child
        counts_q = (
            select(EbayCategory.parent_id, func.count())
            .where(EbayCategory.parent_id.in_(child_ids))
            .group_by(EbayCategory.parent_id)
        )
        counts_result = await db.execute(counts_q)
        return {pid: cnt for pid, cnt in counts_result.all()}


async def get_ancestors(category_id: str) -> list[dict]:
    """Walk up the tree to build breadcrumb trail. Returns list from root to category."""
    ancestors = []
    async with AsyncSessionLocal() as db:
        current_id = category_id
        while current_id:
            result = await db.execute(
                select(EbayCategory).where(EbayCategory.ebay_category_id == current_id)
            )
            cat = result.scalar_one_or_none()
            if cat is None:
                break
            ancestors.append({"ebay_category_id": cat.ebay_category_id, "name": cat.name})
            current_id = cat.parent_id

    ancestors.reverse()
    return ancestors


async def search_categories(query: str, limit: int = 50) -> list[EbayCategory]:
    """Search category names by keyword."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(EbayCategory)
            .where(EbayCategory.name.ilike(f"%{query}%"))
            .order_by(EbayCategory.level, EbayCategory.name)
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_tracked_categories() -> list[EbayCategory]:
    """Get all categories the user has marked as tracked."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(EbayCategory)
            .where(EbayCategory.is_tracked == True)
            .order_by(EbayCategory.avg_profit_margin_pct.desc().nullslast())
        )
        return list(result.scalars().all())


async def set_tracked(category_id: str, tracked: bool) -> bool:
    """Mark a category as tracked/untracked. Returns True if found."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(EbayCategory).where(EbayCategory.ebay_category_id == category_id)
        )
        cat = result.scalar_one_or_none()
        if cat is None:
            return False
        cat.is_tracked = tracked
        await db.commit()
        return True


async def resolve_mymarket_cats(category_id: str) -> Optional[list[int]]:
    """Walk up the tree to find the nearest mymarket category mapping."""
    async with AsyncSessionLocal() as db:
        current_id: Optional[str] = category_id
        while current_id:
            result = await db.execute(
                select(EbayCategory).where(EbayCategory.ebay_category_id == current_id)
            )
            cat = result.scalar_one_or_none()
            if cat is None:
                return None
            if cat.mymarket_cat_ids:
                try:
                    return json.loads(cat.mymarket_cat_ids)
                except json.JSONDecodeError:
                    pass
            current_id = cat.parent_id
    return None


async def resolve_default_weight(category_id: str) -> Optional[float]:
    """Walk up the tree to find the nearest default weight."""
    async with AsyncSessionLocal() as db:
        current_id: Optional[str] = category_id
        while current_id:
            result = await db.execute(
                select(EbayCategory).where(EbayCategory.ebay_category_id == current_id)
            )
            cat = result.scalar_one_or_none()
            if cat is None:
                return None
            if cat.default_weight_kg is not None:
                return cat.default_weight_kg
            current_id = cat.parent_id
    return None


async def get_category_by_id(category_id: str) -> Optional[EbayCategory]:
    """Get a single category by ID."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(EbayCategory).where(EbayCategory.ebay_category_id == category_id)
        )
        return result.scalar_one_or_none()


async def get_leaf_descendants(category_id: str, limit: int = 500) -> list[EbayCategory]:
    """
    Get all leaf categories under a given parent (recursive).
    Uses iterative BFS to find all descendants, then filters to leaves.
    """
    async with AsyncSessionLocal() as db:
        # BFS through the tree to collect all descendant IDs
        queue = [category_id]
        all_ids: list[str] = []
        leaf_ids: list[str] = []

        while queue:
            batch = queue[:100]
            queue = queue[100:]

            result = await db.execute(
                select(EbayCategory).where(EbayCategory.parent_id.in_(batch))
            )
            children = list(result.scalars().all())

            for child in children:
                all_ids.append(child.ebay_category_id)
                if child.is_leaf:
                    leaf_ids.append(child.ebay_category_id)
                else:
                    queue.append(child.ebay_category_id)

                if len(leaf_ids) >= limit:
                    break
            if len(leaf_ids) >= limit:
                break

        # Fetch full leaf category objects
        if not leaf_ids:
            return []
        leaf_ids = leaf_ids[:limit]
        result = await db.execute(
            select(EbayCategory).where(EbayCategory.ebay_category_id.in_(leaf_ids))
        )
        return list(result.scalars().all())


async def count_leaf_descendants(category_id: str) -> int:
    """Count all leaf categories under a given parent (recursive BFS)."""
    async with AsyncSessionLocal() as db:
        queue = [category_id]
        count = 0

        while queue:
            batch = queue[:100]
            queue = queue[100:]

            result = await db.execute(
                select(EbayCategory).where(EbayCategory.parent_id.in_(batch))
            )
            children = list(result.scalars().all())

            for child in children:
                if child.is_leaf:
                    count += 1
                else:
                    queue.append(child.ebay_category_id)

        return count
