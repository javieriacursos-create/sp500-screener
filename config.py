"""
config.py — All filter defaults, scoring weights, and profile presets.
Centralized here so the UI and engine always stay in sync.
"""

# ─── Refresh ────────────────────────────────────────────────────────────────
DEFAULT_REFRESH_MINUTES = 5

# ─── Cache TTLs (seconds) ────────────────────────────────────────────────────
CACHE_TTL_FUNDAMENTALS = 4 * 3600   # 4 hours
CACHE_TTL_PRICE        = 5 * 60     # 5 minutes
CACHE_TTL_UNIVERSE     = 24 * 3600  # 24 hours

# ─── Risk Profile Scoring Weights ────────────────────────────────────────────
SCORING_WEIGHTS = {
    "Conservative": {
        "valuation": 0.40,
        "growth":    0.30,
        "momentum":  0.15,
        "flow":      0.15,
    },
    "Balanced": {
        "valuation": 0.25,
        "growth":    0.25,
        "momentum":  0.25,
        "flow":      0.25,
    },
    "Aggressive": {
        "valuation": 0.10,
        "growth":    0.20,
        "momentum":  0.40,
        "flow":      0.30,
    },
}

DEFAULT_PROFILE = "Balanced"

# ─── Default Filter Thresholds ───────────────────────────────────────────────
DEFAULTS = {
    # Core
    "pe_max":              20.0,
    "volume_spike_min":    2.0,
    "rsi_min":             50.0,

    # Enhanced
    "rev_growth_min":      5.0,    # %
    "earn_growth_min":     5.0,    # %
    "de_ratio_max":        1.5,
    "fcf_positive":        True,
    "roe_min":             10.0,   # %
    "above_50d_ma":        True,
    "above_200d_ma":       True,
    "rs_vs_spy":           True,   # outperformance over 3M

    # Momentum
    "momentum_1m_min":    -999.0,  # no floor by default
    "momentum_3m_min":    -999.0,

    # Display
    "top_n":               20,
    "refresh_minutes":     DEFAULT_REFRESH_MINUTES,
}

# ─── Column Display Config ───────────────────────────────────────────────────
DISPLAY_COLUMNS = [
    "Ticker",
    "Name",
    "Price",
    "PE_Trailing",
    "PE_Forward",
    "Volume_Ratio",
    "RSI",
    "Rev_Growth_%",
    "Earn_Growth_%",
    "ROE_%",
    "Momentum_1M_%",
    "Momentum_3M_%",
    "RS_vs_SPY_%",
    "Score",
]

COLUMN_LABELS = {
    "Ticker":          "Ticker",
    "Name":            "Company",
    "Price":           "Price ($)",
    "PE_Trailing":     "P/E Trailing",
    "PE_Forward":      "P/E Forward",
    "Volume_Ratio":    "Vol Ratio",
    "RSI":             "RSI(14)",
    "Rev_Growth_%":    "Rev Growth %",
    "Earn_Growth_%":   "EPS Growth %",
    "ROE_%":           "ROE %",
    "Momentum_1M_%":   "1M Return %",
    "Momentum_3M_%":   "3M Return %",
    "RS_vs_SPY_%":     "RS vs SPY %",
    "Score":           "Score (0-100)",
}

# ─── Score tier thresholds ───────────────────────────────────────────────────
SCORE_HIGH   = 70   # green highlight
SCORE_MEDIUM = 50   # yellow highlight
