from __future__ import annotations
from typing import Optional

def intrinsic_value(price: float, fcf: float, growth: float = 0.04, discount: float = 0.10,
                    fade_years: int = 10, terminal_growth: float = 0.02, shares: float | None = None) -> Optional[float]:
    """
    Simple FCF-DCF:
    - Years 1..fade_years grow at 'growth' but linearly fade to terminal_growth by year 'fade_years'.
    - Discount each year at 'discount'.
    - Terminal value = FCF_(fade_years+1) / (discount - terminal_growth).
    Returns intrinsic value per share if 'shares' provided; otherwise returns a firm-level value
    that you can compare to price (relative margin-of-safety).
    """
    if fcf is None or fcf <= 0 or discount <= terminal_growth:
        return None
    v = 0.0
    f = fcf
    for y in range(1, fade_years+1):
        g = growth - (growth - terminal_growth) * (y-1)/(fade_years-1) if fade_years > 1 else terminal_growth
        f = f * (1.0 + g)
        v += f / ((1.0 + discount) ** y)
    f_next = f * (1.0 + terminal_growth)
    term = f_next / (discount - terminal_growth)
    v += term / ((1.0 + discount) ** (fade_years+1))
    if shares and shares > 0:
        return v / shares
    return v