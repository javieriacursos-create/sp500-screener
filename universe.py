"""
universe.py — Dynamically fetches and caches the S&P 500 constituent list.
Primary source: Wikipedia. Fallback: hardcoded sample for offline resilience.
"""

import os
import io
import pickle
import time
import logging
import requests
import pandas as pd

from config import CACHE_TTL_UNIVERSE

CACHE_DIR   = os.path.join(os.path.dirname(__file__), "cache")
CACHE_FILE  = os.path.join(CACHE_DIR, "sp500_universe.pkl")
WIKI_URL    = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

logger = logging.getLogger(__name__)


def _load_cache():
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        with open(CACHE_FILE, "rb") as f:
            data = pickle.load(f)
        if time.time() - data["ts"] < CACHE_TTL_UNIVERSE:
            return data["tickers"]
    except Exception:
        pass
    return None


def _save_cache(tickers: list):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_FILE, "wb") as f:
        pickle.dump({"ts": time.time(), "tickers": tickers}, f)


def get_sp500_tickers() -> list:
    """
    Returns a list of S&P 500 ticker symbols (strings).
    Uses Wikipedia as the primary source; caches for 24 hours.
    """
    cached = _load_cache()
    if cached:
        logger.info(f"Universe loaded from cache: {len(cached)} tickers")
        return cached

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/122.0.0.0 Safari/537.36"
        }
        resp = requests.get(WIKI_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text), attrs={"id": "constituents"}, header=0)
        df = tables[0]
        tickers = (
            df["Symbol"]
            .str.replace(".", "-", regex=False)   # BRK.B → BRK-B for yfinance
            .tolist()
        )
        names    = df["Security"].tolist()
        name_map = dict(zip(tickers, names))
        _save_cache(tickers)
        _save_name_map(name_map)
        logger.info(f"Universe fetched from Wikipedia: {len(tickers)} tickers")
        return tickers

    except Exception as e:
        logger.warning(f"Wikipedia fetch failed ({e}), using built-in S&P 500 seed list.")

    # ── Hardcoded fallback: representative S&P 500 tickers (updated 2025)
    FALLBACK_TICKERS = [
        "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","BRK-B","GOOG","JPM",
        "LLY","V","UNH","XOM","MA","AVGO","PG","HD","COST","JNJ","ABBV","MRK","CVX",
        "CRM","BAC","NFLX","AMD","PEP","KO","TMO","ADBE","ORCL","ACN","MCD","CSCO",
        "LIN","ABT","TXN","WMT","DHR","PM","INTC","CMCSA","IBM","GE","INTU","CAT",
        "GS","SPGI","RTX","HON","T","BLK","AMGN","NOW","ISRG","BKNG","ELV","SYK",
        "MDLZ","VRTX","REGN","AXP","PLD","DE","ADI","TJX","MMC","LRCX","BSX",
        "ETN","ZTS","MO","CB","AON","CI","GILD","CME","SO","KLAC","DUK","ITW",
        "PGR","NOC","GD","SHW","MCO","F","GM","USB","PNC","MS","WFC","C","COF",
        "MMM","EMR","APD","ECL","HCA","HUM","CVS","WBA","ANTM","UNP","CSX","NSC",
        "FDX","UPS","LMT","BA","SBUX","NKE","LOW","TGT","EBAY","PYPL","SQ","SNOW",
        "PLTR","PANW","CRWD","ZS","DDOG","NET","OKTA","TWLO","MDB","TTD",
        "UBER","LYFT","ABNB","DASH","RBLX","COIN","HOOD","RIVN","LCID",
        "ENPH","FSLR","NEE","AEP","EXC","PCG","ED","FE","CNP","NRG",
        "VZ","TMUS","CHTR","DISH","LUMN","FOXA","DIS","PARA","WBD",
        "PFE","BMY","BIIB","ILMN","MRNA","BNTX","VTRS","HLT","MAR","H","CCL","RCL",
        "DAL","UAL","AAL","LUV","WH","IHG","WYNN","LVS","MGM","PENN",
        "SPG","AMT","EQIX","PSA","EQR","AVB","VTR","WELL","O","WPC",
        "GLD","SLV","USO","UNG","DBA","DBB","DBC","PDBC","IAU","SIVR",
    ]
    # Remove duplicates while preserving order
    seen, unique = set(), []
    for t in FALLBACK_TICKERS:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    _save_cache(unique)
    logger.info(f"Using hardcoded fallback: {len(unique)} tickers")
    return unique


def _save_name_map(name_map: dict):
    path = os.path.join(CACHE_DIR, "sp500_names.pkl")
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(name_map, f)


def get_name_map() -> dict:
    """Returns {ticker: company_name} mapping."""
    path = os.path.join(CACHE_DIR, "sp500_names.pkl")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    # Trigger a fresh fetch to populate names
    get_sp500_tickers()
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tickers = get_sp500_tickers()
    print(f"Loaded {len(tickers)} tickers. First 10: {tickers[:10]}")
