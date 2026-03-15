"""
Modern tracking advisor service:
- Scores categories for auto-tracking
- Chooses weekly focus bucket
- Applies hybrid auto+manual tracking decisions
- Writes tracking audit records
"""
import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select

from backend.config import settings
from backend.database import AsyncSessionLocal
from backend.models import EbayCategory, ModernCategoryRefreshStat, ModernOpportunity, ModernTrackingAudit, Setting


_FOCUS_BUCKETS = ("electronics_small", "antiques_decor", "mixed")


@dataclass
class TrackingConfig:
    tracking_mode: str = "hybrid_auto_manual"
    auto_track_enabled: bool = True
    auto_track_max_categories: int = 40
    auto_track_refresh_hours: int = 24
    auto_track_min_liquidity: float = 0.10
    auto_track_min_score: float = 0.35
    focus_policy: str = "weekly_winner"
    focus_bucket: str = "auto"
    focus_last_decided_at: str = ""
    realism_max_extreme_margin_pct: float = 500.0
    realism_min_positive_discount_share: float = 0.20


def _as_bool(raw: str, default: bool) -> bool:
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _as_float(raw: Optional[str], default: float) -> float:
    try:
        return float(raw) if raw is not None else default
    except Exception:
        return default


def _as_int(raw: Optional[str], default: int) -> int:
    try:
        return int(float(raw)) if raw is not None else default
    except Exception:
        return default


def _parse_dt(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def classify_focus_bucket(category_name: str) -> str:
    name = (category_name or "").lower()
    electronics_keywords = [
        "phone", "iphone", "smart", "tablet", "ipad", "laptop", "notebook", "camera",
        "video game", "console", "xbox", "playstation", "nintendo", "pc", "electronics",
        "watch", "wearable", "headphone", "audio", "monitor",
    ]
    antiques_keywords = [
        "antique", "vintage", "collect", "architectural", "maritime", "primitive", "art deco",
        "furniture", "home decor", "mirror", "sideboard", "buffet", "table", "chest", "trunk",
        "jars", "bottles", "jewelry", "ethnographic", "old",
    ]
    if any(k in name for k in electronics_keywords):
        return "electronics_small"
    if any(k in name for k in antiques_keywords):
        return "antiques_decor"
    return "mixed"


async def _load_settings_map() -> dict[str, str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Setting))
        return {row.key: row.value for row in result.scalars().all()}


def parse_tracking_config(raw: dict[str, str]) -> TrackingConfig:
    return TrackingConfig(
        tracking_mode=raw.get("modern_tracking_mode", settings.modern_tracking_mode),
        auto_track_enabled=_as_bool(raw.get("modern_auto_track_enabled"), settings.modern_auto_track_enabled),
        auto_track_max_categories=max(1, _as_int(raw.get("modern_auto_track_max_categories"), settings.modern_auto_track_max_categories)),
        auto_track_refresh_hours=max(1, _as_int(raw.get("modern_auto_track_refresh_hours"), settings.modern_auto_track_refresh_hours)),
        auto_track_min_liquidity=max(0.0, min(1.0, _as_float(raw.get("modern_auto_track_min_liquidity"), settings.modern_auto_track_min_liquidity))),
        auto_track_min_score=max(0.0, min(1.0, _as_float(raw.get("modern_auto_track_min_score"), settings.modern_auto_track_min_score))),
        focus_policy=raw.get("modern_focus_policy", settings.modern_focus_policy),
        focus_bucket=raw.get("modern_focus_bucket", settings.modern_focus_bucket),
        focus_last_decided_at=raw.get("modern_focus_last_decided_at", settings.modern_focus_last_decided_at),
        realism_max_extreme_margin_pct=max(50.0, _as_float(raw.get("modern_realism_max_extreme_margin_pct"), settings.modern_realism_max_extreme_margin_pct)),
        realism_min_positive_discount_share=max(0.0, min(1.0, _as_float(raw.get("modern_realism_min_positive_discount_share"), settings.modern_realism_min_positive_discount_share))),
    )


async def get_tracking_config() -> TrackingConfig:
    raw = await _load_settings_map()
    return parse_tracking_config(raw)


async def _upsert_settings(updates: dict[str, str]):
    now = datetime.utcnow()
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(Setting).where(Setting.key.in_(list(updates.keys()))))).scalars().all()
        by_key = {s.key: s for s in existing}
        for key, value in updates.items():
            row = by_key.get(key)
            if row is None:
                db.add(Setting(key=key, value=value, updated_at=now))
            else:
                row.value = value
                row.updated_at = now
        await db.commit()


async def choose_focus_bucket(cfg: TrackingConfig, force_recompute: bool = False) -> tuple[str, dict[str, dict[str, float]]]:
    now = datetime.utcnow()
    last_decided = _parse_dt(cfg.focus_last_decided_at)
    explicit_bucket = cfg.focus_bucket if cfg.focus_bucket in _FOCUS_BUCKETS else "auto"

    if (
        cfg.focus_policy == "weekly_winner"
        and not force_recompute
        and explicit_bucket in _FOCUS_BUCKETS
        and last_decided is not None
        and (now - last_decided) < timedelta(days=7)
    ):
        return explicit_bucket, {}

    cutoff = now - timedelta(days=14)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(
                ModernOpportunity.ebay_category_id,
                ModernOpportunity.demand_gate_passed,
                ModernOpportunity.final_score,
                ModernOpportunity.projected_discount_pct,
                ModernOpportunity.profit_margin_pct,
                ModernOpportunity.profit_usd,
            ).where(ModernOpportunity.last_scored_at >= cutoff)
        )).all()
        cat_rows = (await db.execute(select(EbayCategory.ebay_category_id, EbayCategory.name))).all()

    cat_name_map = {cid: name for cid, name in cat_rows}
    bucket_rows: dict[str, list[tuple[bool, float, Optional[float], Optional[float], Optional[float]]]] = {
        "electronics_small": [],
        "antiques_decor": [],
        "mixed": [],
    }

    for cat_id, gate_passed, final_score, projected_discount_pct, profit_margin_pct, profit_usd in rows:
        bucket = classify_focus_bucket(cat_name_map.get(cat_id, ""))
        bucket_rows[bucket].append((
            bool(gate_passed),
            float(final_score or 0.0),
            projected_discount_pct,
            profit_margin_pct,
            profit_usd,
        ))

    metrics: dict[str, dict[str, float]] = {}
    max_qualified = 1
    max_profit = 1.0
    for bucket, values in bucket_rows.items():
        qualified = sum(1 for v in values if v[0])
        profits = [max(0.0, float(v[4] or 0.0)) for v in values]
        max_qualified = max(max_qualified, qualified)
        max_profit = max(max_profit, (statistics.mean(profits) if profits else 0.0))

    winner = "mixed"
    winner_score = -1.0
    for bucket, values in bucket_rows.items():
        qualified = sum(1 for v in values if v[0])
        finals = [v[1] for v in values]
        median_final = statistics.median(finals) if finals else 0.0

        realism_pass = 0
        for _, _, projected_discount_pct, profit_margin_pct, _ in values:
            ok_discount = projected_discount_pct is None or projected_discount_pct > 0
            ok_margin = profit_margin_pct is None or profit_margin_pct <= cfg.realism_max_extreme_margin_pct
            if ok_discount and ok_margin:
                realism_pass += 1
        realism_share = (realism_pass / len(values)) if values else 0.0

        profits = [max(0.0, float(v[4] or 0.0)) for v in values]
        avg_profit = statistics.mean(profits) if profits else 0.0

        qual_norm = qualified / max_qualified
        final_norm = min(1.0, median_final / 100.0)
        profit_norm = avg_profit / max_profit if max_profit > 0 else 0.0
        score = 0.45 * qual_norm + 0.25 * final_norm + 0.15 * realism_share + 0.15 * profit_norm

        metrics[bucket] = {
            "qualified": float(qualified),
            "median_final_score": round(median_final, 3),
            "realism_pass_share": round(realism_share, 4),
            "avg_profit_usd": round(avg_profit, 4),
            "bucket_score": round(score, 4),
        }

        if score > winner_score:
            winner_score = score
            winner = bucket

    if all(len(v) == 0 for v in bucket_rows.values()):
        winner = "mixed"

    await _upsert_settings({
        "modern_focus_bucket": winner,
        "modern_focus_last_decided_at": now.isoformat(),
    })
    return winner, metrics


def _calc_category_score(
    *,
    liquidity_score: float,
    qualification_score: float,
    comparables_score: float,
    realism_score: float,
    stability_score: float,
) -> float:
    return max(0.0, min(1.0, (
        0.30 * liquidity_score
        + 0.25 * qualification_score
        + 0.20 * comparables_score
        + 0.15 * realism_score
        + 0.10 * stability_score
    )))


async def build_tracking_recommendations(
    cfg: TrackingConfig,
    force_focus_recompute: bool = False,
) -> dict[str, Any]:
    focus_bucket, focus_metrics = await choose_focus_bucket(cfg, force_recompute=force_focus_recompute)
    now = datetime.utcnow()
    cutoff = now - timedelta(days=14)

    async with AsyncSessionLocal() as db:
        categories = list((await db.execute(select(EbayCategory).where(EbayCategory.is_leaf == True))).scalars().all())
        stats_rows = list((await db.execute(select(ModernCategoryRefreshStat))).scalars().all())
        opp_rows = (await db.execute(
            select(
                ModernOpportunity.ebay_category_id,
                ModernOpportunity.projected_discount_pct,
                ModernOpportunity.profit_margin_pct,
                ModernOpportunity.georgian_listing_count,
                ModernOpportunity.confidence_score,
                ModernOpportunity.demand_score,
                ModernOpportunity.profit_usd,
            ).where(ModernOpportunity.last_scored_at >= cutoff)
        )).all()

    stats_map = {s.category_id: s for s in stats_rows}
    opp_map: dict[str, list[tuple[Optional[float], Optional[float], int, float, float, Optional[float]]]] = {}
    for cat_id, projected_discount_pct, profit_margin_pct, georgian_listing_count, confidence_score, demand_score, profit_usd in opp_rows:
        opp_map.setdefault(cat_id, []).append((
            projected_discount_pct,
            profit_margin_pct,
            int(georgian_listing_count or 0),
            float(confidence_score or 0.0),
            float(demand_score or 0.0),
            profit_usd,
        ))

    recs: list[dict[str, Any]] = []
    for cat in categories:
        stat = stats_map.get(cat.ebay_category_id)
        processed = int(stat.processed_count) if stat else 0
        shortlisted = int(stat.shortlisted_count) if stat else 0
        qualified = int(stat.qualified_count) if stat else 0

        opps = opp_map.get(cat.ebay_category_id, [])
        opp_count = len(opps)

        liquidity_score = min(1.0, processed / 30.0)
        qualification_score = (qualified / max(shortlisted, 1)) if shortlisted > 0 else 0.0

        comparables_hits = sum(1 for _, _, listing_count, _, _, _ in opps if listing_count >= 2)
        comparables_score = (comparables_hits / opp_count) if opp_count > 0 else 0.0

        realism_fail = 0
        positive_discount = 0
        for projected_discount_pct, profit_margin_pct, *_ in opps:
            if projected_discount_pct is not None and projected_discount_pct > 0:
                positive_discount += 1
            bad_discount = projected_discount_pct is not None and projected_discount_pct <= 0
            bad_margin = profit_margin_pct is not None and profit_margin_pct > cfg.realism_max_extreme_margin_pct
            if bad_discount or bad_margin:
                realism_fail += 1
        realism_score = (1.0 - (realism_fail / opp_count)) if opp_count > 0 else 0.0

        stability_score = min(1.0, shortlisted / 20.0)

        avg_confidence = statistics.mean([o[3] for o in opps]) if opps else 0.0
        avg_demand = statistics.mean([o[4] for o in opps]) if opps else 0.0
        data_health_score = (avg_confidence + avg_demand) / 2.0

        score = _calc_category_score(
            liquidity_score=liquidity_score,
            qualification_score=qualification_score,
            comparables_score=comparables_score,
            realism_score=realism_score,
            stability_score=stability_score,
        )

        reasons: list[str] = []
        hard_drop = False

        if processed <= 0 and not cat.manual_pin:
            hard_drop = True
            reasons.append("no_stage_a_activity")
        if shortlisted >= 3 and comparables_score < 0.20:
            hard_drop = True
            reasons.append("persistent_low_comparables")
        if opp_count >= 3 and realism_score < 0.20:
            hard_drop = True
            reasons.append("severe_realism_failure")

        if opp_count > 0:
            pos_discount_share = positive_discount / opp_count
            if pos_discount_share < cfg.realism_min_positive_discount_share:
                reasons.append("low_positive_discount_share")

        source = "manual" if (cat.manual_pin or cat.manual_block) else (cat.track_source or "none")
        focus_match = focus_bucket == "mixed" or classify_focus_bucket(cat.name) == focus_bucket
        if not focus_match and not cat.manual_pin:
            reasons.append("focus_bucket_filtered")

        decision = "hold"
        if cat.manual_block:
            decision = "drop"
            reasons.insert(0, "manual_block")
        elif cat.manual_pin:
            decision = "track"
            reasons.insert(0, "manual_pin")
        elif not focus_match:
            decision = "drop"
        elif hard_drop:
            decision = "drop"
        elif score >= cfg.auto_track_min_score and liquidity_score >= cfg.auto_track_min_liquidity:
            decision = "track"
        elif cat.is_tracked and cat.track_source == "auto":
            decision = "drop"

        recs.append({
            "category_id": cat.ebay_category_id,
            "category_name": cat.name,
            "is_leaf": bool(cat.is_leaf),
            "is_tracked": bool(cat.is_tracked),
            "source": source,
            "category_track_score": round(score, 4),
            "factor_breakdown": {
                "liquidity": round(liquidity_score, 4),
                "qualification": round(qualification_score, 4),
                "comparables": round(comparables_score, 4),
                "realism": round(realism_score, 4),
                "stability": round(stability_score, 4),
                "data_health": round(data_health_score, 4),
            },
            "decision": decision,
            "reasons": reasons,
        })

    recs.sort(
        key=lambda r: (
            1 if "manual_pin" in r["reasons"] else 0,
            1 if r["decision"] == "track" else 0,
            r["category_track_score"],
            r["factor_breakdown"]["liquidity"],
        ),
        reverse=True,
    )

    return {
        "focus_bucket": focus_bucket,
        "focus_metrics": focus_metrics,
        "recommendations": recs,
    }


async def apply_tracking_recommendations(
    cfg: TrackingConfig,
    recommendations: list[dict[str, Any]],
    focus_bucket: str,
) -> dict[str, int]:
    now = datetime.utcnow()
    manual_pins = [r for r in recommendations if "manual_pin" in r.get("reasons", [])]
    track_candidates = [
        r for r in recommendations
        if r["decision"] == "track" and "manual_pin" not in r.get("reasons", []) and "manual_block" not in r.get("reasons", [])
    ]
    selected_auto = {r["category_id"] for r in track_candidates[: cfg.auto_track_max_categories]}
    selected_manual = {r["category_id"] for r in manual_pins}

    metrics = {
        "scanned": len(recommendations),
        "manual_skipped": 0,
        "added": 0,
        "kept": 0,
        "removed": 0,
    }

    async with AsyncSessionLocal() as db:
        cats = list((await db.execute(select(EbayCategory).where(EbayCategory.is_leaf == True))).scalars().all())
        by_id = {c.ebay_category_id: c for c in cats}

        for rec in recommendations:
            cat = by_id.get(rec["category_id"])
            if cat is None:
                continue

            old_tracked = bool(cat.is_tracked)
            reasons = rec.get("reasons", [])
            decision = rec.get("decision", "hold")

            if cat.manual_block:
                cat.is_tracked = False
                cat.track_source = "manual"
                metrics["manual_skipped"] += 1
                audit_decision = "skipped_manual"
            elif cat.manual_pin:
                cat.is_tracked = True
                cat.track_source = "manual"
                metrics["manual_skipped"] += 1
                audit_decision = "skipped_manual"
            else:
                should_track = rec["category_id"] in selected_auto or rec["category_id"] in selected_manual
                if should_track:
                    cat.is_tracked = True
                    cat.track_source = "auto"
                    cat.auto_track_score = rec.get("category_track_score")
                    cat.auto_tracked_at = now
                    audit_decision = "kept" if old_tracked else "added"
                    metrics["kept" if old_tracked else "added"] += 1
                else:
                    cat.is_tracked = False
                    cat.track_source = "none"
                    cat.auto_track_score = rec.get("category_track_score")
                    audit_decision = "removed" if old_tracked else "kept"
                    if old_tracked:
                        metrics["removed"] += 1

            db.add(ModernTrackingAudit(
                run_at=now,
                focus_bucket=focus_bucket,
                category_id=cat.ebay_category_id,
                score=rec.get("category_track_score"),
                decision=audit_decision,
                reasons_json=json.dumps({
                    "decision": decision,
                    "source": rec.get("source"),
                    "reasons": reasons,
                    "factor_breakdown": rec.get("factor_breakdown", {}),
                }),
            ))

        await db.commit()

    return metrics


async def run_tracking_advisor(
    *,
    apply_changes: bool,
    force_focus_recompute: bool = False,
) -> dict[str, Any]:
    cfg = await get_tracking_config()
    rec_result = await build_tracking_recommendations(cfg, force_focus_recompute=force_focus_recompute)

    apply_metrics = {
        "scanned": len(rec_result["recommendations"]),
        "manual_skipped": 0,
        "added": 0,
        "kept": 0,
        "removed": 0,
    }
    if apply_changes and cfg.auto_track_enabled and settings.modern_tracking_advisor_enabled:
        apply_metrics = await apply_tracking_recommendations(
            cfg,
            rec_result["recommendations"],
            rec_result["focus_bucket"],
        )

    return {
        "config": cfg,
        "focus_bucket": rec_result["focus_bucket"],
        "focus_metrics": rec_result["focus_metrics"],
        "recommendations": rec_result["recommendations"],
        "apply_metrics": apply_metrics,
    }


async def list_recent_audit(limit: int = 100) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        rows = list((await db.execute(
            select(ModernTrackingAudit).order_by(ModernTrackingAudit.run_at.desc(), ModernTrackingAudit.id.desc()).limit(limit)
        )).scalars().all())

    out = []
    for row in rows:
        reasons = {}
        if row.reasons_json:
            try:
                reasons = json.loads(row.reasons_json)
            except json.JSONDecodeError:
                reasons = {}
        out.append({
            "id": row.id,
            "run_at": row.run_at,
            "focus_bucket": row.focus_bucket,
            "category_id": row.category_id,
            "score": row.score,
            "decision": row.decision,
            "reasons": reasons,
        })
    return out


async def advisor_is_stale(cfg: TrackingConfig) -> bool:
    if not cfg.auto_track_enabled:
        return False
    if not settings.modern_tracking_advisor_enabled:
        return False

    async with AsyncSessionLocal() as db:
        last_run = (await db.execute(select(func.max(ModernTrackingAudit.run_at)))).scalar_one_or_none()

    if last_run is None:
        return True
    return (datetime.utcnow() - last_run) >= timedelta(hours=cfg.auto_track_refresh_hours)


async def maybe_run_advisor_before_refresh() -> Optional[dict[str, Any]]:
    cfg = await get_tracking_config()
    if not await advisor_is_stale(cfg):
        return None
    return await run_tracking_advisor(apply_changes=True, force_focus_recompute=False)
