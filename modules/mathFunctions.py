from __future__ import annotations

from typing import Dict, Any

from modules import configFunctions

config_location = "/config/config.yml"


def _cfg() -> Dict[str, Any]:
    return configFunctions.get_config(config_location) or {}


def _get(d: Dict, path: list, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p, default)
    return cur if cur is not None else default


def _round2(x):
    try:
        return round(float(x), 2)
    except Exception:
        return x


def _nearly_equal(a: float, b: float, eps: float = 0.01) -> bool:
    return abs(float(a) - float(b)) <= eps


def _first_time_prices(cfg: Dict, server: str, is_4k: str) -> Dict[str, float] | None:
    promos = _get(cfg, ["promotions", "first_time_prices"], {})
    if not isinstance(promos, dict):
        return None
    res_key = "4k" if is_4k == "Yes" else "1080p"
    server_block = promos.get(server)
    if not isinstance(server_block, dict):
        return None
    plan = server_block.get(res_key)
    if not isinstance(plan, dict):
        return None
    out = {}
    for k, v in plan.items():
        ks = str(k)
        if ks.endswith("Month"):
            out[ks] = float(v)
        else:
            try:
                m = int(ks)
                out[f"{m}Month"] = float(v)
            except Exception:
                pass
    return out or None


def _standard_prices(cfg: Dict, server: str, is_4k: str) -> Dict[str, float]:
    plex_block = _get(cfg, [f"PLEX-{server}"], {}) or {}
    res_key = "4k" if is_4k == "Yes" else "1080p"
    plan = plex_block.get(res_key, {}) or {}
    return {
        "1Month": float(plan.get("1Month", 0) or 0),
        "3Month": float(plan.get("3Month", 0) or 0),
        "6Month": float(plan.get("6Month", 0) or 0),
        "12Month": float(plan.get("12Month", 0) or 0),
    }


def calculate_term_length(server: str, amount: float, is_4k: str) -> int:
    """
    Derive subscription term (months) from an amount.
    - Prefer promotions.first_time_prices for this server/plan (exact match)
    - Otherwise, fall back to your standard exact/iterative packing logic.
    """
    cfg = _cfg()
    amt = _round2(amount)

    # First-time fixed prices (new user case)
    ft = _first_time_prices(cfg, server, is_4k)
    if ft:
        for months, key in ((12, "12Month"), (6, "6Month"), (3, "3Month"), (1, "1Month")):
            price = ft.get(key)
            if price is not None and _nearly_equal(amt, _round2(price)):
                return months
        # If not an exact promo match, fall back to standard logic below.

    # Standard table
    std = _standard_prices(cfg, server, is_4k)
    one_m = _round2(std.get("1Month", 0))
    three_m = _round2(std.get("3Month", 0))
    six_m = _round2(std.get("6Month", 0))
    twelve_m = _round2(std.get("12Month", 0))

    # Exact tier matches
    if _nearly_equal(amt, twelve_m):
        return 12
    if _nearly_equal(amt, six_m):
        return 6
    if _nearly_equal(amt, three_m):
        return 3
    if _nearly_equal(amt, one_m):
        return 1

    # Iterative packing (12→6→3→1)
    term_length = 0
    remaining = amt

    if twelve_m > 0:
        while remaining + 1e-9 >= twelve_m:
            term_length += 12
            remaining = _round2(remaining - twelve_m)

    if six_m > 0:
        while remaining + 1e-9 >= six_m:
            term_length += 6
            remaining = _round2(remaining - six_m)

    if three_m > 0:
        while remaining + 1e-9 >= three_m:
            term_length += 3
            remaining = _round2(remaining - three_m)

    if one_m > 0:
        while remaining + 1e-9 >= one_m:
            term_length += 1
            remaining = _round2(remaining - one_m)

    if term_length > 0:
        return term_length

    return 0
