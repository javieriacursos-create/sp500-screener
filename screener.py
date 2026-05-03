"""
screener.py — Core screening pipeline and composite scoring engine.

Flow:
  1. Fetch S&P 500 universe
  2. Download price histories (batched)
  3. Fetch fundamentals (per-ticker, cached)
  4. Compute technical indicators
  5. Apply filters
  6. Score and rank

All filter params passed as a dict to allow UI-driven overrides.
"""

import logging
import time
import numpy as np
import pandas as pd

from universe      import get_sp500_tickers, get_name_map
from data_fetcher  import get_price_history, get_spy_history, get_fundamentals, get_batch_closes
from indicators    import (
    calc_rsi, calc_volume_ratio, calc_volume_trend,
    calc_momentum, calc_relative_strength,
    price_above_ma,
)
from config        import DEFAULTS, SCORING_WEIGHTS

logger = logging.getLogger(__name__)


# ─── Main screening function ──────────────────────────────────────────────────

def run_screener(
    filters: None  = None,
    profile: str          = "Balanced",
    progress_callback     = None,   # callable(int pct, str msg)
    max_tickers: int      = 505,    # set lower for testing
) -> pd.DataFrame:
    """
    Runs the full screening pipeline. Returns a ranked DataFrame.
    `filters` overrides DEFAULTS for any keys provided.
    """
    cfg = {**DEFAULTS, **(filters or {})}
    weights = SCORING_WEIGHTS.get(profile, SCORING_WEIGHTS["Balanced"])

    def _progress(pct, msg):
        if progress_callback:
            progress_callback(pct, msg)
        logger.info(f"[{pct}%] {msg}")

    # 1. Universe
    _progress(2, "Fetching S&P 500 universe…")
    try:
        tickers = get_sp500_tickers()[:max_tickers]
    except Exception as e:
        logger.error(f"Universe fetch failed: {e}")
        return pd.DataFrame()

    name_map = get_name_map()

    # 2. SPY benchmark
    _progress(5, "Downloading SPY benchmark…")
    spy_hist = get_spy_history()
    spy_close = spy_hist["Close"] if spy_hist is not None and not spy_hist.empty else None

    # 3. Batch price download
    _progress(10, f"Downloading price history for {len(tickers)} tickers…")
    batch = get_batch_closes(tickers, period="1y")

    # 4. Per-ticker processing
    rows = []
    n = len(tickers)

    for i, ticker in enumerate(tickers):
        pct = 10 + int((i / n) * 75)
        if i % 25 == 0:
            _progress(pct, f"Processing {ticker} ({i}/{n})…")

        row = _process_ticker(
            ticker, batch, spy_close, cfg, name_map
        )
        if row is not None:
            rows.append(row)

    if not rows:
        _progress(100, "No data returned.")
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # 5. Apply filters
    _progress(87, "Applying filters…")
    df = _apply_filters(df, cfg)

    if df.empty:
        _progress(100, "No stocks passed all filters.")
        return df

    # 6. Score & rank
    _progress(93, "Computing composite scores…")
    df = _score(df, weights)
    df = df.sort_values("Score", ascending=False).reset_index(drop=True)
    df.index = df.index + 1   # 1-based rank

    _progress(100, f"Done. {len(df)} stocks passed filters.")
    return df


# ─── Per-ticker data assembly ─────────────────────────────────────────────────

def _process_ticker(ticker, batch, spy_close, cfg, name_map) -> None:
    """Assembles all metrics for one ticker. Returns None if price data missing."""
    hist = None

    # Try batch first, fall back to individual fetch
    if ticker in batch and len(batch[ticker]) > 10:
        close  = batch[ticker]
        # We need full OHLCV for volume — fetch individually
        full   = get_price_history(ticker)
        volume = full["Volume"] if full is not None and "Volume" in full.columns else None
    else:
        full = get_price_history(ticker)
        if full is None or full.empty:
            return None
        close  = full["Close"]
        volume = full["Volume"] if "Volume" in full.columns else None

    if close is None or len(close) < 20:
        return None

    # Technicals
    rsi           = calc_rsi(close)
    vol_ratio     = calc_volume_ratio(volume) if volume is not None else None
    vol_trend     = calc_volume_trend(volume) if volume is not None else None
    mom_1m        = calc_momentum(close, 21)
    mom_3m        = calc_momentum(close, 63)
    above_50d     = price_above_ma(close, 50)
    above_200d    = price_above_ma(close, 200)
    rs_vs_spy     = calc_relative_strength(close, spy_close, 63) if spy_close is not None else None
    current_price = round(float(close.iloc[-1]), 2)

    # Fundamentals (cached)
    fund = get_fundamentals(ticker)

    return {
        "Ticker":          ticker,
        "Name":            fund.get("name") or name_map.get(ticker, ticker),
        "Sector":          fund.get("sector"),
        "Price":           current_price,
        "PE_Trailing":     fund.get("pe_trailing"),
        "PE_Forward":      fund.get("pe_forward"),
        "Revenue_Growth":  fund.get("revenue_growth"),
        "Earn_Growth":     fund.get("earnings_growth"),
        "DE_Ratio":        fund.get("de_ratio"),
        "FCF":             fund.get("fcf"),
        "ROE":             fund.get("roe"),
        "ROIC":            fund.get("roic"),
        "RSI":             rsi,
        "Volume_Ratio":    vol_ratio,
        "Vol_Trend":       vol_trend,
        "Momentum_1M":     mom_1m,
        "Momentum_3M":     mom_3m,
        "Above_50d":       above_50d,
        "Above_200d":      above_200d,
        "RS_vs_SPY":       rs_vs_spy,
    }


# ─── Filter application ───────────────────────────────────────────────────────

def _apply_filters(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    mask = pd.Series([True] * len(df), index=df.index)

    # P/E filter — prefer forward if available
    pe_col = df.apply(
        lambda r: r["PE_Forward"] if r["PE_Forward"] is not None and not np.isnan(float(r["PE_Forward"] or np.nan))
                  else r["PE_Trailing"],
        axis=1
    )
    mask &= pe_col.apply(lambda v: _passes(v, max_val=cfg["pe_max"]))

    # Volume spike
    mask &= df["Volume_Ratio"].apply(lambda v: _passes(v, min_val=cfg["volume_spike_min"]))

    # RSI
    mask &= df["RSI"].apply(lambda v: _passes(v, min_val=cfg["rsi_min"]))

    # Revenue growth
    mask &= df["Revenue_Growth"].apply(lambda v: _passes(v, min_val=cfg["rev_growth_min"]))

    # Earnings growth
    mask &= df["Earn_Growth"].apply(lambda v: _passes(v, min_val=cfg["earn_growth_min"]))

    # D/E ratio
    mask &= df["DE_Ratio"].apply(lambda v: _passes(v, max_val=cfg["de_ratio_max"]))

    # FCF positive
    if cfg.get("fcf_positive", True):
        mask &= df["FCF"].apply(lambda v: v is not None and not np.isnan(float(v or np.nan)) and float(v) > 0)

    # ROE — use ROIC as fallback
    roe_series = df.apply(
        lambda r: r["ROE"] if r["ROE"] is not None else r["ROIC"], axis=1
    )
    mask &= roe_series.apply(lambda v: _passes(v, min_val=cfg["roe_min"]))

    # Moving average filters
    if cfg.get("above_50d_ma", True):
        mask &= df["Above_50d"].apply(lambda v: v is True)
    if cfg.get("above_200d_ma", True):
        mask &= df["Above_200d"].apply(lambda v: v is True)

    # Relative strength
    if cfg.get("rs_vs_spy", True):
        mask &= df["RS_vs_SPY"].apply(lambda v: _passes(v, min_val=0.0))

    return df[mask].copy()


def _passes(val, min_val=None, max_val=None) -> bool:
    """Safe filter check that returns False for None/NaN."""
    try:
        v = float(val)
        if np.isnan(v) or np.isinf(v):
            return False
        if min_val is not None and v < min_val:
            return False
        if max_val is not None and v > max_val:
            return False
        return True
    except Exception:
        return False


# ─── Composite scoring ────────────────────────────────────────────────────────

def _score(df: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """
    Scores each stock 0–100 across 4 pillars.
    Uses percentile ranking within the filtered universe.
    """
    df = df.copy()

    def _pct_rank(series: pd.Series, ascending=True) -> pd.Series:
        """Rank series to 0–100 percentile. Higher rank = better."""
        ranks = series.rank(ascending=ascending, pct=True, na_option="bottom")
        return ranks * 100

    # Valuation (lower P/E better, higher FCF yield better)
    pe_eff = df.apply(
        lambda r: r["PE_Forward"] if r["PE_Forward"] is not None else r["PE_Trailing"], axis=1
    ).fillna(999)
    v_pe  = _pct_rank(pe_eff, ascending=False)   # lower P/E = higher score

    fcf_yield = df.apply(
        lambda r: (r["FCF"] / (r["Price"] * 1e6)) if r["FCF"] else None, axis=1
    ).fillna(0)
    v_fcf = _pct_rank(fcf_yield, ascending=True)

    val_score = (v_pe * 0.6 + v_fcf * 0.4).clip(0, 100)

    # Growth
    rev  = df["Revenue_Growth"].fillna(0)
    earn = df["Earn_Growth"].fillna(0)
    growth_score = (
        _pct_rank(rev,  ascending=True) * 0.5 +
        _pct_rank(earn, ascending=True) * 0.5
    ).clip(0, 100)

    # Momentum
    m1   = df["Momentum_1M"].fillna(0)
    m3   = df["Momentum_3M"].fillna(0)
    rsi  = df["RSI"].fillna(50)
    mom_score = (
        _pct_rank(m1,  ascending=True) * 0.35 +
        _pct_rank(m3,  ascending=True) * 0.45 +
        _pct_rank(rsi, ascending=True) * 0.20
    ).clip(0, 100)

    # Volume/Flow
    vr   = df["Volume_Ratio"].fillna(1)
    vt   = df["Vol_Trend"].fillna(1)
    rs   = df["RS_vs_SPY"].fillna(0)
    flow_score = (
        _pct_rank(vr, ascending=True) * 0.40 +
        _pct_rank(vt, ascending=True) * 0.25 +
        _pct_rank(rs, ascending=True) * 0.35
    ).clip(0, 100)

    # Composite
    w = weights
    df["Score_Valuation"] = val_score.round(1)
    df["Score_Growth"]    = growth_score.round(1)
    df["Score_Momentum"]  = mom_score.round(1)
    df["Score_Flow"]      = flow_score.round(1)
    df["Score"] = (
        val_score  * w["valuation"] +
        growth_score * w["growth"] +
        mom_score  * w["momentum"] +
        flow_score * w["flow"]
    ).round(1)

    return df


# ─── Output formatting ────────────────────────────────────────────────────────

def format_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Renames and rounds columns for clean UI display."""
    if df.empty:
        return df

    out = df[[
        "Ticker", "Name", "Sector", "Price",
        "PE_Trailing", "PE_Forward",
        "Volume_Ratio", "RSI",
        "Revenue_Growth", "Earn_Growth",
        "ROE",
        "Momentum_1M", "Momentum_3M",
        "RS_vs_SPY",
        "Score",
        "Score_Valuation", "Score_Growth", "Score_Momentum", "Score_Flow",
    ]].copy()

    out.columns = [
        "Ticker", "Company", "Sector", "Price ($)",
        "P/E Trailing", "P/E Forward",
        "Vol Ratio", "RSI",
        "Rev Growth %", "EPS Growth %",
        "ROE %",
        "1M Ret %", "3M Ret %",
        "RS vs SPY %",
        "Score",
        "Val Score", "Growth Score", "Mom Score", "Flow Score",
    ]

    # Round numerics
    for col in ["Price ($)", "P/E Trailing", "P/E Forward", "Vol Ratio", "RSI",
                "Rev Growth %", "EPS Growth %", "ROE %",
                "1M Ret %", "3M Ret %", "RS vs SPY %",
                "Score", "Val Score", "Growth Score", "Mom Score", "Flow Score"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").round(2)

    return out
