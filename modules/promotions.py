from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from modules import configFunctions

CONFIG_PATH = "/config/config.yml"


@dataclass
class PromoOutcome:
    subtotal_before_discounts: float
    final_price: float
    intro_applied: bool
    double_discount_applied: bool
    applied_discount_percent: float
    notes: str


@dataclass
class ReferralReward:
    days_to_extend: int


def _cfg() -> Dict:
    return configFunctions.get_config(CONFIG_PATH) or {}


def _get(d: Dict, path: list, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p, default)
    return cur if cur is not None else default


def _round2(x: float) -> float:
    return round(float(x), 2)


def _first_time_fixed_price(cfg: Dict, server: str, quality: str, months: int) -> Optional[float]:
    promos = _get(cfg, ["promotions", "first_time_prices"], {})
    if not isinstance(promos, dict):
        return None
    res_key = "4k" if quality.strip().lower() == "4k" else "1080p"
    server_block = promos.get(server)
    if not isinstance(server_block, dict):
        return None
    plan = server_block.get(res_key)
    if not isinstance(plan, dict):
        return None
    key = f"{months}Month"
    val = plan.get(key, plan.get(str(months)))
    return float(val) if val is not None else None


def price_for_new_user_first_purchase(
    *,
    base_monthly_price: float,
    months: int,
    quality: str,
    server: str,
    config: Optional[Dict] = None,
) -> PromoOutcome:
    """
    Compute first-purchase price for new user:
      1) Use promotions.first_time_prices fixed number if present.
      2) Else fall back to non-discounted subtotal (kept for safety).
    """
    cfg = (config or {}) or _cfg()
    base_subtotal = float(base_monthly_price) * int(months)

    fixed = _first_time_fixed_price(cfg, server, quality, months)
    if fixed is not None:
        return PromoOutcome(
            subtotal_before_discounts=_round2(base_subtotal),
            final_price=_round2(fixed),
            intro_applied=(months == 1),
            double_discount_applied=(months in (3, 6, 12)),
            applied_discount_percent=0.0,
            notes=f"first-time fixed price ({months} mo) from config",
        )

    # Fallback: no promo configured—return subtotal
    return PromoOutcome(
        subtotal_before_discounts=_round2(base_subtotal),
        final_price=_round2(base_subtotal),
        intro_applied=False,
        double_discount_applied=False,
        applied_discount_percent=0.0,
        notes="no first-time promo configured",
    )


def referral_reward_for_new_user_first_purchase(*, months: int, config: Optional[Dict] = None) -> Optional[ReferralReward]:
    """
    Read referrals.rewards_by_months and return days to extend referrer.
    Accepts keys like "1", "3", "6", "12".
    """
    cfg = (config or {}) or _cfg()
    user = (cfg or {}).get("referrals", {})
    enabled = bool(user.get("enabled", True))
    if not enabled:
        return None

    rbm = user.get("rewards_by_months", {"1": 7, "3": 14, "6": 30, "12": 60})
    days = None
    if str(months) in rbm:
        days = rbm[str(months)]
    elif months in rbm:
        days = rbm[months]
    if days is None:
        return None
    try:
        return ReferralReward(days_to_extend=int(days))
    except Exception:
        return None
