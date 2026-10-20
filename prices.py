"""Stage 3a: daily POLYCAB.NS price and volume from yfinance -> data/processed/prices.csv.

Run once from the command line; the app's Refresh button calls fetch_prices() again.
"""
from pathlib import Path
import pandas as pd
import yfinance as yf

TICKER = "POLYCAB.NS"
OUT = Path(__file__).parent / "data/processed/prices.csv"


def fetch_prices(path=OUT):
    df = yf.Ticker(TICKER).history(period="max", interval="1d", auto_adjust=False)
    if df.empty:
        raise RuntimeError(f"yfinance returned no data for {TICKER}")
    df = df.reset_index()
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None).dt.normalize()
    df = df.rename(columns=str.lower).rename(columns={"adj close": "adj_close"})
    df = df[["date", "open", "high", "low", "close", "adj_close", "volume"]].dropna(subset=["close"])
    df.to_csv(path, index=False)
    return df


if __name__ == "__main__":
    d = fetch_prices()
    print(d.shape, d.date.min().date(), d.date.max().date(), "last close", round(d.close.iloc[-1], 2))
