"""
Calibrated Swing Screener Proximity Radar Service.

Decouples screener setup levels (Best Buy, Target 1/2/3, Stop Loss, Technical Verification)
from live CMP quotes so radar quotes, percentage distances, stage classification, and summary
KPI counters remain fresh across all 10 NSE sector universes with one bulk quote request.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.core.logging_config import get_logger
from backend.core.market_hours import is_indian_market_open

logger = get_logger(__name__)


def _canonical_sym(sym: str | None) -> str:
    if not sym:
        return ""
    return str(sym).upper().strip().replace(".NS", "").replace(".BO", "")


def _normalize_ts(ts_val: Any) -> str | None:
    if isinstance(ts_val, str) and ts_val.strip():
        return ts_val.strip()
    if isinstance(ts_val, datetime):
        dt = ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return None


async def build_screener_proximity_radar(
    sector: str = "ALL",
    proximity_pct: float = 3.0,
    min_score: float = 60.0,
    stage: str = "ALL",
    force_refresh: bool = False,
) -> dict:
    """
    Assemble screener candidates across 1 or all 10 sectors, overlay LIVE bulk quotes in
    1 single API call, apply strict stage & ±proximity bounds, and reconcile KPI counts
    with the displayed radar table.
    """
    from backend.core.cache import cache_get
    from backend.services.market_data import market_data_service
    from backend.services.screener import SECTOR_UNIVERSES, ScreenerService, resolve_stock_sector

    norm_sector = sector.upper().replace(" ", "_") if sector else "ALL"
    norm_stage = stage.upper() if stage else "ALL"
    prox = max(0.2, float(proximity_pct or 3.0))

    candidates_raw: list[dict] = []
    sectors_loaded: list[str] = []
    scan_timestamps: list[str] = []

    def _collect_from_payload(sec_label: str, payload: Any, prefer_top: bool = False) -> None:
        if not isinstance(payload, dict):
            return
        ts_str = _normalize_ts(payload.get("timestamp"))
        if ts_str:
            scan_timestamps.append(ts_str)
        rows = payload.get("buy_stocks") or []
        if not rows and payload.get("all_results"):
            rows = [r for r in payload.get("all_results", []) if isinstance(r, dict) and r.get("action") == "BUY"]
        if not rows:
            return
        if sec_label not in sectors_loaded:
            sectors_loaded.append(sec_label)
        for s in rows:
            if not isinstance(s, dict):
                continue
            s_copy = dict(s)
            if sec_label not in ("ALL", "AGGREGATED", "LKG_ALL"):
                s_copy.setdefault("sector", sec_label)
            if prefer_top:
                candidates_raw.insert(0, s_copy)
            else:
                candidates_raw.append(s_copy)

    if norm_sector == "ALL":
        # 1. Read multi-sector aggregate + every cached/LKG sector so ALL never drops IT/Banking/Mid/Small caps
        cached_agg = await cache_get("screener_all_sectors_aggregated")
        if cached_agg and isinstance(cached_agg, dict):
            _collect_from_payload("ALL", cached_agg, prefer_top=True)
            for sec_s in (cached_agg.get("sectors_scanned") or []):
                if sec_s not in sectors_loaded:
                    sectors_loaded.append(sec_s)

        for sec_name in SECTOR_UNIVERSES.keys():
            sec_cached = await cache_get(f"screener_results_{sec_name}")
            if sec_cached and isinstance(sec_cached, dict) and (sec_cached.get("buy_stocks") or sec_cached.get("all_results")):
                _collect_from_payload(sec_name, sec_cached)
                continue
            sec_lkg = await cache_get(f"screener_lkg_{sec_name}")
            if sec_lkg and isinstance(sec_lkg, dict) and (sec_lkg.get("buy_stocks") or sec_lkg.get("all_results")):
                _collect_from_payload(sec_name, sec_lkg)

        if not candidates_raw:
            agg_lkg = await cache_get("screener_all_sectors_lkg")
            if agg_lkg and isinstance(agg_lkg, dict):
                _collect_from_payload("LKG_ALL", agg_lkg)

        if not candidates_raw:
            try:
                res = await ScreenerService.run_screener(sector="NIFTY_50", force_refresh=force_refresh)
                _collect_from_payload("NIFTY_50", res)
            except Exception as e:
                logger.warning(f"Radar cold-start fallback NIFTY_50 scan failed: {e}")
    else:
        sec_cached = await cache_get(f"screener_results_{norm_sector}")
        if sec_cached and isinstance(sec_cached, dict) and "buy_stocks" in sec_cached:
            _collect_from_payload(norm_sector, sec_cached)
        else:
            sec_lkg = await cache_get(f"screener_lkg_{norm_sector}")
            if sec_lkg and isinstance(sec_lkg, dict) and "buy_stocks" in sec_lkg:
                _collect_from_payload(norm_sector, sec_lkg)

        if not candidates_raw:
            try:
                res = await ScreenerService.run_screener(sector=norm_sector, force_refresh=force_refresh)
                if res and isinstance(res, dict):
                    _collect_from_payload(norm_sector, res)
            except Exception as e:
                logger.warning(f"Radar sector {norm_sector} scan failed: {e}")

    # Canonical deduplication: retain highest-conviction setup per canonical symbol
    by_canon: dict[str, dict] = {}
    for s in candidates_raw:
        sym = str(s.get("symbol") or "").upper().strip()
        canon = _canonical_sym(sym)
        if not canon:
            continue
        plan = s.get("trade_plan") or {}
        best_buy = plan.get("best_buy_price") or plan.get("optimal_entry_price") or plan.get("entry_price")
        score = float(s.get("total_score") or 0.0)
        if not (best_buy and float(best_buy) > 0 and score >= min_score):
            continue

        existing = by_canon.get(canon)
        if existing is None:
            by_canon[canon] = s
        else:
            existing_score = float(existing.get("total_score") or 0.0)
            existing_has_t123 = bool((existing.get("trade_plan") or {}).get("target_1"))
            new_has_t123 = bool(plan.get("target_1"))
            if (score > existing_score) or (score == existing_score and new_has_t123 and not existing_has_t123):
                by_canon[canon] = s

    valid_candidates = list(by_canon.values())
    now_iso = datetime.now(timezone.utc).isoformat()
    latest_scan_ts = max(scan_timestamps) if scan_timestamps else None

    if not valid_candidates:
        return {
            "sector": norm_sector,
            "stage": norm_stage,
            "proximity_threshold_pct": prox,
            "total_candidates": 0,
            "generated_at": now_iso,
            "quote_timestamp": None,
            "scan_timestamp": latest_scan_ts,
            "sectors_loaded": sectors_loaded,
            "quotes_live_count": 0,
            "is_market_open": is_indian_market_open(),
            "summary": {
                "at_best_buy": 0,
                "near_best_buy": 0,
                "pre_buy_prime": 0,
                "approaching": 0,
                "sell_pre_alerts": 0,
                "below_buy": 0,
            },
            "candidates": [],
        }

    # Always overlay LIVE quotes in ONE SINGLE BULK CALL via FyersRateGovernor
    symbols_to_quote = [str(s["symbol"]).upper().strip() for s in valid_candidates]
    quotes_map: dict[str, dict] = {}
    try:
        quotes_map = await market_data_service.fetch_quotes_bulk(
            symbols_to_quote,
            use_fallback=True,
            bypass_cache=force_refresh,
        ) or {}
    except Exception as e:
        logger.warning(f"Radar bulk quote fetch failed, falling back to scan prices: {e}")
        quotes_map = {}

    quote_timestamps: list[str] = []
    live_quote_hits = 0
    radar_items: list[dict] = []

    at_best_buy_count = 0
    near_best_buy_count = 0
    approaching_count = 0
    sell_pre_alert_count = 0
    below_buy_count = 0

    for s in valid_candidates:
        sym = str(s["symbol"]).upper().strip()
        canon = _canonical_sym(sym)
        plan = s.get("trade_plan") or {}
        best_buy = float(plan.get("best_buy_price") or plan.get("optimal_entry_price") or plan.get("entry_price") or 0.0)
        target_1 = float(plan["target_1"]) if plan.get("target_1") else None
        target_2 = float(plan["target_2"]) if plan.get("target_2") else None
        target_3 = float(plan["target_3"]) if plan.get("target_3") else None
        target = float(plan.get("target_price") or target_2 or target_1 or 0.0)
        sl = float(plan.get("stop_loss") or 0.0)

        quote = (
            quotes_map.get(sym)
            or quotes_map.get(f"{canon}.NS")
            or quotes_map.get(f"{canon}.BO")
            or quotes_map.get(canon)
            or {}
        )
        live_price = float(quote.get("price") or 0.0)
        if live_price > 0:
            live_quote_hits += 1
            q_ts = _normalize_ts(quote.get("timestamp"))
            if q_ts:
                quote_timestamps.append(q_ts)
            cmp = live_price
        else:
            cmp = float(plan.get("current_price") or plan.get("cmp") or best_buy)
            if cmp <= 0:
                cmp = best_buy

        distance_pct = round(((cmp - best_buy) / best_buy) * 100.0, 2) if best_buy > 0 else 0.0
        abs_dist = abs(distance_pct)

        # 1. Strict Stage Classification (PRE_BUY excludes AT_BEST_BUY ±0.5%)
        is_at_best_buy = abs_dist <= 0.5
        is_pre_buy = (distance_pct > 0.5) and (distance_pct <= prox)
        pre_buy_diff = round(max(0.0, cmp - best_buy), 2)
        pre_buy_buffer_pct = max(0.0, distance_pct)

        # 2. Target Proximity & Sell Pre-Alert Determination
        if target > 0 and cmp > 0:
            target_distance_pct = round(((target - cmp) / cmp) * 100.0, 2)
            is_near_target = 0.0 <= target_distance_pct <= 2.5
            is_target_hit = target_distance_pct <= 0.0
        else:
            target_distance_pct = 999.0
            is_near_target = False
            is_target_hit = False

        if is_near_target:
            sell_pre_alert_label = f"🎯 Near Target (Sell Pre-Alert: +{target_distance_pct}% to T2: ₹{target:.2f})"
        elif is_target_hit:
            sell_pre_alert_label = f"🚀 Target Reached (CMP ₹{cmp:.2f} >= Target ₹{target:.2f})"
        else:
            sell_pre_alert_label = None

        # 3. Proximity status categorization
        if is_at_best_buy:
            status = "AT_BEST_BUY"
            status_label = "🎯 At Best Buy (Optimal Immediate Entry)"
        elif 0.5 < distance_pct <= 2.0:
            status = "NEAR_BEST_BUY"
            status_label = f"⚡ Pre-Buy Zone (+{distance_pct}% before Best Buy)"
        elif 2.0 < distance_pct <= max(4.0, prox):
            status = "APPROACHING"
            status_label = f"⏳ Approaching Pre-Buy (+{distance_pct}% before Best Buy)"
        elif distance_pct < -0.5:
            status = "BELOW_BUY"
            status_label = f"🏷️ Slipped Below Buy ({distance_pct}% discount)"
        else:
            status = "EXTENDED"
            status_label = f"🚀 Extended from Best Buy (+{distance_pct}%)"

        # 4. Top Analyzers Multi-Factor Constraints Verification
        indicators = s.get("indicators") or {}
        rsi = float(indicators.get("rsi_14") or s.get("rsi") or 50.0)
        ai_res = s.get("ai_analysis") or {}
        ml_conf = float(ai_res.get("confidence") or s.get("confidence") or (s.get("total_score", 70) / 100.0))
        ml_prob_buy = float((ai_res.get("probabilities") or {}).get("buy", 0.60))
        rr_ratio = round(float(plan.get("risk_reward_ratio") or 2.0), 2)

        passed_constraints = []
        if 30.0 <= rsi <= 65.0:
            passed_constraints.append("RSI Momentum in Accumulation Zone (30-65)")
        if rr_ratio >= 1.7:
            passed_constraints.append(f"Favorable Asymmetric R:R ({rr_ratio}:1)")
        if ml_prob_buy >= 0.50:
            passed_constraints.append(f"ML Directional Conviction ({int(ml_prob_buy * 100)}% Buy Prob)")
        if float(s.get("total_score") or 0.0) >= 65.0:
            passed_constraints.append("Multi-Factor Confluence (Score >= 65)")
        if sl > 0 and cmp > sl:
            passed_constraints.append("Structural Stop Loss Buffer Intact")

        is_verified = len(passed_constraints) >= 3
        verdict = "TOP_ANALYZER_VERIFIED" if is_verified else "STANDARD_SETUP"
        verdict_label = "✓ Top Analyzer Verified" if is_verified else "⚡ Standard Setup"

        # 5. Strict Stage + ±Proximity Filter
        if norm_stage == "PRE_BUY":
            matches_stage = is_pre_buy
        elif norm_stage == "SELL_PRE_ALERT":
            matches_stage = is_near_target
        elif norm_stage == "AT_BEST_BUY":
            matches_stage = is_at_best_buy
        else:  # "ALL"
            matches_stage = (abs_dist <= prox) or is_near_target

        if not matches_stage:
            continue

        # Count KPI summary strictly from matching setups so counts reconcile 100%
        if is_at_best_buy:
            at_best_buy_count += 1
        elif 0.5 < distance_pct <= 2.0:
            near_best_buy_count += 1
        elif 2.0 < distance_pct <= max(4.0, prox):
            approaching_count += 1
        elif distance_pct < -0.5:
            below_buy_count += 1

        if is_near_target:
            sell_pre_alert_count += 1

        raw_sec = s.get("sector")
        if not raw_sec or raw_sec in ("ALL", "AGGREGATED", "LKG_ALL"):
            raw_sec = resolve_stock_sector(sym)

        live_expected_gain = (
            round(((target - cmp) / cmp) * 100.0, 1)
            if (target > 0 and cmp > 0)
            else round(float(plan.get("expected_gain_pct") or 0.0), 1)
        )

        radar_items.append({
            "symbol": sym,
            "name": s.get("name") or sym,
            "sector": raw_sec,
            "action": s.get("action", "BUY"),
            "total_score": round(float(s.get("total_score") or 0.0), 1),
            "cmp": round(cmp, 2),
            "best_buy_price": round(best_buy, 2),
            "entry_type": plan.get("entry_type", "PULLBACK_DIP"),
            "distance_pct": distance_pct,
            "abs_distance_pct": abs_dist,
            "is_at_best_buy": is_at_best_buy,
            "is_pre_buy": is_pre_buy,
            "pre_buy_diff": pre_buy_diff,
            "pre_buy_buffer_pct": pre_buy_buffer_pct,
            "is_near_target": is_near_target,
            "target_distance_pct": target_distance_pct,
            "sell_pre_alert_label": sell_pre_alert_label,
            "proximity_status": status,
            "proximity_label": status_label,
            "target_price": round(target, 2) if target else 0.0,
            "target_1": round(target_1, 2) if target_1 else None,
            "target_2": round(target_2, 2) if target_2 else None,
            "target_3": round(target_3, 2) if target_3 else None,
            "stop_loss": round(sl, 2) if sl else 0.0,
            "expected_gain_pct": live_expected_gain,
            "risk_reward_ratio": rr_ratio,
            "risk_buffer_pct": round(((cmp - sl) / cmp) * 100.0, 2) if sl > 0 and cmp > 0 else 0.0,
            "quote_timestamp": _normalize_ts(quote.get("timestamp")),
            "technical_verification": {
                "verified": is_verified,
                "verdict": verdict,
                "verdict_label": verdict_label,
                "rsi": round(rsi, 1),
                "risk_reward": rr_ratio,
                "ml_confidence": round(ml_conf, 2),
                "ml_buy_prob": round(ml_prob_buy, 2),
                "passed_constraints": passed_constraints,
                "total_constraints_passed": len(passed_constraints),
            },
        })

    if norm_stage == "SELL_PRE_ALERT":
        radar_items.sort(key=lambda x: (x["target_distance_pct"], -x["total_score"]))
    else:
        radar_items.sort(key=lambda x: (x["abs_distance_pct"], -x["total_score"]))

    pre_buy_count = near_best_buy_count + (approaching_count if norm_stage == "PRE_BUY" or prox > 2.0 else 0)

    return {
        "sector": norm_sector,
        "stage": norm_stage,
        "proximity_threshold_pct": prox,
        "total_candidates": len(radar_items),
        "generated_at": now_iso,
        "quote_timestamp": max(quote_timestamps) if quote_timestamps else None,
        "scan_timestamp": latest_scan_ts,
        "sectors_loaded": sectors_loaded,
        "quotes_live_count": live_quote_hits,
        "is_market_open": is_indian_market_open(),
        "summary": {
            "at_best_buy": at_best_buy_count,
            "near_best_buy": near_best_buy_count,
            "pre_buy_prime": pre_buy_count,
            "approaching": approaching_count,
            "sell_pre_alerts": sell_pre_alert_count,
            "below_buy": below_buy_count,
        },
        "candidates": radar_items,
    }
