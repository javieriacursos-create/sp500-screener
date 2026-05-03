"""
data_fetcher.py — All yfinance data retrieval with TTL-based file caching.
Handles missing data gracefully: returns None fields rather than crashing.
"""

import os
import pickle
import time
import logging
import yfinance as yf
import pandas as pd
import numpy as np

from config import CACHE_TTL_FUNDAMENTALS, CACHE_TTL_PRICE

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
logger    = logging.getLogger(__name__)


# ─── Cache helpers ────────────────────────────────────────────────────────────

def _cache_path(key: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    safe = key.replace("/", "_").replace("\\", "_")
    return os.path.join(CACHE_DIR, f"{safe}.pkl")


def _cache_get(key: str, ttl: int):
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
        if time.time() - data["ts"] < ttl:
            return data["value"]
    except Exception:
        pass
    return None


def _cache_set(key: str, value):
    path = _cache_path(key)
    try:
        with open(path, "wb") as f:
            pickle.dump({"ts": time.time(), "value": value}, f)
    except Exception as e:
        logger.warning(f"Cache write failed for {key}: {e}")


# ─── Price history ────────────────────────────────────────────────────────────

def get_price_history(ticker: str, period: str = "1y") -> None:
    """
    Returns OHLCV DataFrame for ticker. Cached at CACHE_TTL_PRICE seconds.
    Returns None on failure.
    """
    key = f"price_{ticker}_{period}"
    cached = _cache_get(key, CACHE_TTL_PRICE)
    if cached is not None:
        return cached
    try:
        df = yf.download(
            ticker,
            period=period,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if df is None or df.empty:
            return None
        # Flatten multi-level columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        _cache_set(key, df)
        return df
    except Exception as e:
        logger.debug(f"Price history failed for {ticker}: {e}")
        return None


def get_spy_history(period: str = "1y") -> None:
    """SPY benchmark price history."""
    return get_price_history("SPY", period)


# ─── Fundamentals ─────────────────────────────────────────────────────────────

def _safe(val):
    """Convert to float or return None."""
    try:
        v = float(val)
        return None if (np.isnan(v) or np.isinf(v)) else v
    except Exception:
        return None


def get_fundamentals(ticker: str) -> dict:
    """
    Returns a dict of fundamental metrics for the ticker.
    All values are float or None — never raises.
    """
    key = f"fund_{ticker}"
    cached = _cache_get(key, CACHE_TTL_FUNDAMENTALS)
    if cached is not None:
        return cached

    result = {
        "pe_trailing":    None,
        "pe_forward":     None,
        "revenue_growth": None,   # YoY %
        "earnings_growth":None,   # YoY %
        "de_ratio":       None,
        "fcf":            None,
        "roe":            None,
        "roic":           None,
        "market_cap":     None,
        "sector":         None,
        "name":           ticker,
    }

    try:
        tk   = yf.Ticker(ticker)
        info = tk.info or {}

        result["name"]         = info.get("longName") or info.get("shortName") or ticker
        result["sector"]       = info.get("sector")
        result["pe_trailing"]  = _safe(info.get("trailingPE"))
        result["pe_forward"]   = _safe(info.get("forwardPE"))
        result["de_ratio"]     = _safe(info.get("debtToEquity"))
        result["roe"]          = _safe(info.get("returnOnEquity"))
        result["market_cap"]   = _safe(info.get("marketCap"))

        # Revenue growth
        rev_growth = info.get("revenueGrowth")
        if rev_growth is not None:
            result["revenue_growth"] = _safe(rev_growth * 100)

        # Earnings growth
        earn_growth = info.get("earningsGrowth")
        if earn_growth is not None:
            result["earnings_growth"] = _safe(earn_growth * 100)

        # Free Cash Flow
        fcf = info.get("freeCashflow")
        result["fcf"] = _safe(fcf)

        # ROE — yfinance returns as decimal
        if result["roe"] is not None:
            result["roe"] = round(result["roe"] * 100, 2)

        # ROIC: not directly in info, approximate from financials
        try:
            bs  = tk.balance_sheet
            cf  = tk.cashflow
            inc = tk.financials
            if bs is not None and not bs.empty and inc is not None and not inc.empty:
                # Invested capital = total assets - current liabilities (approx)
                ta_row = next((r for r in ["Total Assets"] if r in bs.index), None)
                cl_row = next((r for r in ["Current Liabilities", "Total Current Liabilities"] if r in bs.index), None)
                ni_row = next((r for r in ["Net Income"] if r in inc.index), None)
                if ta_row and cl_row and ni_row:
                    ta = float(bs.loc[ta_row].iloc[0])
                    cl = float(bs.loc[cl_row].iloc[0])
                    ni = float(inc.loc[ni_row].iloc[0])
                    ic = ta - cl
                    if ic > 0:
                        result["roic"] = round(ni / ic * 100, 2)
        except Exception:
            pass

        # Try income statement for YoY growth if info fields are missing
        if result["revenue_growth"] is None:
            try:
                fin = tk.financials
                if fin is not None and not fin.empty:
                    rev_row = next((r for r in ["Total Revenue", "Revenue"] if r in fin.index), None)
                    if rev_row and fin.shape[1] >= 2:
                        r0 = float(fin.loc[rev_row].iloc[0])
                        r1 = float(fin.loc[rev_row].iloc[1])
                        if r1 != 0:
                            result["revenue_growth"] = round((r0 - r1) / abs(r1) * 100, 2)
            except Exception:
                pass

        if result["earnings_growth"] is None:
            try:
                fin = tk.financials
                if fin is not None and not fin.empty:
                    ni_row = next((r for r in ["Net Income"] if r in fin.index), None)
                    if ni_row and fin.shape[1] >= 2:
                        e0 = float(fin.loc[ni_row].iloc[0])
                        e1 = float(fin.loc[ni_row].iloc[1])
                        if e1 != 0:
                            result["earnings_growth"] = round((e0 - e1) / abs(e1) * 100, 2)
            except Exception:
                pass

    except Exception as e:
        logger.debug(f"Fundamentals failed for {ticker}: {e}")

    _cache_set(key, result)
    return result


# ─── Batch price fetch ────────────────────────────────────────────────────────

def get_batch_closes(tickers: list, period: str = "1y") -> dict:
    """
    Efficiently downloads close prices for multiple tickers at once.
    Returns {ticker: pd.Series} mapping.
    """
    key = f"batch_close_{'_'.join(sorted(tickers[:5]))}_{len(tickers)}_{period}"
    cached = _cache_get(key, CACHE_TTL_PRICE)
    if cached is not None:
        return cached

    try:
        raw = yf.download(
            tickers,
            period=period,
            auto_adjust=True,
            progress=False,
            threads=True,
        )
        if raw is None or raw.empty:
            return {}

        # Extract Close
        if isinstance(raw.columns, pd.MultiIndex):
            if "Close" in raw.columns.get_level_values(0):
                closes = raw["Close"]
            else:
                return {}
        else:
            if "Close" in raw.columns:
                closes = raw[["Close"]]
                closes.columns = tickers[:1]
            else:
                return {}

        result = {t: closes[t].dropna() for t in closes.columns if t in tickers}
        _cache_set(key, result)
        return result
    except Exception as e:
        logger.debug(f"Batch close fetch error: {e}")
        return {}
