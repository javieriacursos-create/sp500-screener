"""
indicators.py — Technical indicator calculations using price history DataFrames.
All functions accept a pandas DataFrame with a 'Close' column (and 'Volume' where needed).
Returns scalar values or Series; never raises — returns None on failure.
"""

import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


# ─── RSI ─────────────────────────────────────────────────────────────────────

def calc_rsi(close: pd.Series, period: int = 14) -> None:
    """Returns current RSI(period) as a float, or None if insufficient data."""
    try:
        if len(close) < period + 1:
            return None
        delta = close.diff()
        gain  = delta.where(delta > 0, 0.0).rolling(period).mean()
        loss  = (-delta.where(delta < 0, 0.0)).rolling(period).mean()
        rs    = gain / loss.replace(0, np.nan)
        rsi   = 100 - (100 / (1 + rs))
        val   = rsi.iloc[-1]
        return round(float(val), 2) if not np.isnan(val) else None
    except Exception as e:
        logger.debug(f"RSI calc error: {e}")
        return None


# ─── Moving Averages ─────────────────────────────────────────────────────────

def calc_sma(close: pd.Series, period: int) -> None:
    try:
        if len(close) < period:
            return None
        val = close.rolling(period).mean().iloc[-1]
        return round(float(val), 4) if not np.isnan(val) else None
    except Exception as e:
        logger.debug(f"SMA calc error: {e}")
        return None


def price_above_ma(close: pd.Series, period: int) -> bool:
    """True if last close > SMA(period)."""
    sma = calc_sma(close, period)
    if sma is None or len(close) == 0:
        return False
    return float(close.iloc[-1]) > sma


# ─── Volume ──────────────────────────────────────────────────────────────────

def calc_volume_ratio(volume: pd.Series, lookback: int = 20) -> None:
    """Current volume / avg(last N days). Returns None if insufficient data."""
    try:
        if len(volume) < lookback + 1:
            return None
        avg = volume.iloc[-(lookback + 1):-1].mean()
        if avg == 0:
            return None
        ratio = float(volume.iloc[-1]) / float(avg)
        return round(ratio, 2)
    except Exception as e:
        logger.debug(f"Volume ratio error: {e}")
        return None


def calc_volume_trend(volume: pd.Series, short: int = 20, long: int = 50) -> None:
    """Ratio of short-term avg volume to long-term avg volume."""
    try:
        if len(volume) < long:
            return None
        avg_short = volume.iloc[-short:].mean()
        avg_long  = volume.iloc[-long:].mean()
        if avg_long == 0:
            return None
        return round(float(avg_short) / float(avg_long), 3)
    except Exception as e:
        logger.debug(f"Volume trend error: {e}")
        return None


# ─── Price Momentum ───────────────────────────────────────────────────────────

def calc_momentum(close: pd.Series, days: int) -> None:
    """Return % change over last N trading days."""
    try:
        if len(close) < days + 1:
            return None
        start = float(close.iloc[-(days + 1)])
        end   = float(close.iloc[-1])
        if start == 0:
            return None
        return round((end - start) / start * 100, 2)
    except Exception as e:
        logger.debug(f"Momentum calc error: {e}")
        return None


# ─── Relative Strength vs Benchmark ──────────────────────────────────────────

def calc_relative_strength(
    close: pd.Series,
    bench_close: pd.Series,
    days: int = 63   # ~3 months trading days
) -> None:
    """
    Returns outperformance of stock vs benchmark over N days (in %).
    Positive = outperforming.
    """
    try:
        stock_ret = calc_momentum(close, days)
        bench_ret = calc_momentum(bench_close, days)
        if stock_ret is None or bench_ret is None:
            return None
        return round(stock_ret - bench_ret, 2)
    except Exception as e:
        logger.debug(f"RS calc error: {e}")
        return None
