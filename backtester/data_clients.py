from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Literal

import pandas as pd
import requests


class DataClientError(RuntimeError):
    pass


DataMode = Literal["intraday", "daily", "weekly", "monthly"]
DataProvider = Literal["alpha", "yahoo"]


@dataclass(slots=True)
class CandleRequest:
    symbol: str
    provider: DataProvider
    mode: DataMode
    interval: str | None
    lookback_days: int


class AlphaVantageClient:
    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.requests_made = 0

    def get_requests_remaining(self) -> int:
        return max(0, 25 - self.requests_made)

    def fetch_candles(self, req: CandleRequest) -> pd.DataFrame:
        if req.mode == "intraday":
            raise DataClientError("Alpha Vantage intraday is not enabled in this app. Use Yahoo for intraday data.")

        params: dict[str, str] = {
            "apikey": self.api_key,
            "symbol": req.symbol.upper(),
        }

        if req.mode == "daily":
            params.update({"function": "TIME_SERIES_DAILY_ADJUSTED", "outputsize": "full", "datatype": "json"})
            key = "Time Series (Daily)"
        elif req.mode == "weekly":
            params.update({"function": "TIME_SERIES_WEEKLY", "datatype": "json"})
            key = "Weekly Time Series"
        elif req.mode == "monthly":
            params.update({"function": "TIME_SERIES_MONTHLY", "datatype": "json"})
            key = "Monthly Time Series"
        else:
            raise DataClientError(f"Unsupported data mode for Alpha Vantage: {req.mode}")

        response = requests.get(self.BASE_URL, params=params, timeout=30)
        self.requests_made += 1
        response.raise_for_status()
        payload = response.json()

        if "Note" in payload:
            raise DataClientError(payload["Note"])
        if "Error Message" in payload:
            raise DataClientError(payload["Error Message"])
        if key not in payload:
            serialized_payload = json.dumps(payload, ensure_ascii=False)
            raise DataClientError(
                "Alpha Vantage did not return expected candle data. "
                f"Expected key '{key}'. Full response: {serialized_payload}"
            )

        frame = (
            pd.DataFrame.from_dict(payload[key], orient="index")
            .rename(columns={
                "1. open": "open",
                "2. high": "high",
                "3. low": "low",
                "4. close": "close",
                "5. volume": "volume",
                "6. volume": "volume",
            })
            .astype(float, errors="ignore")
        )
        frame.index = pd.to_datetime(frame.index, utc=True)
        frame = frame.sort_index()

        cutoff = datetime.now(timezone.utc) - timedelta(days=req.lookback_days)
        frame = frame[frame.index >= cutoff]
        if frame.empty:
            raise DataClientError("No candles available for requested lookback period.")
        return frame[["open", "high", "low", "close", "volume"]].fillna(0.0)


class YahooFinanceClient:
    BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
    INTERVAL_MAP = {
        "1min": "1m",
        "5min": "5m",
        "15min": "15m",
        "30min": "30m",
        "60min": "60m",
        "1day": "1d",
        "1week": "1wk",
        "1month": "1mo",
    }

    def fetch_candles(self, req: CandleRequest) -> pd.DataFrame:
        interval = self.INTERVAL_MAP.get(req.interval or "1day")
        if not interval:
            raise DataClientError(f"Unsupported Yahoo interval: {req.interval}")

        period = self._period_from_lookback(req.lookback_days, req.mode)
        response = requests.get(
            f"{self.BASE_URL}/{req.symbol.upper()}",
            params={"interval": interval, "range": period},
            timeout=30,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        response.raise_for_status()
        payload = response.json()

        chart = payload.get("chart", {})
        results = chart.get("result") or []
        if not results:
            error = chart.get("error")
            message = error.get("description") if isinstance(error, dict) else "Yahoo Finance returned no result."
            raise DataClientError(message)

        result = results[0]
        quote = (((result.get("indicators") or {}).get("quote") or [{}])[0])
        timestamps = result.get("timestamp") or []
        if not timestamps:
            raise DataClientError("Yahoo Finance returned no candle data for the request.")

        frame = pd.DataFrame(
            {
                "open": quote.get("open", []),
                "high": quote.get("high", []),
                "low": quote.get("low", []),
                "close": quote.get("close", []),
                "volume": quote.get("volume", []),
            },
            index=pd.to_datetime(timestamps, unit="s", utc=True),
        )

        frame = frame.dropna(subset=["open", "high", "low", "close"]).astype(float)
        cutoff = datetime.now(timezone.utc) - timedelta(days=req.lookback_days)
        frame = frame[frame.index >= cutoff]
        if frame.empty:
            raise DataClientError("No Yahoo candles available for requested lookback period.")
        return frame.fillna(0.0)

    @staticmethod
    def _period_from_lookback(lookback_days: int, mode: DataMode) -> str:
        if mode == "intraday":
            if lookback_days <= 7:
                return "7d"
            if lookback_days <= 60:
                return "60d"
            return "730d"
        if lookback_days <= 30:
            return "1mo"
        if lookback_days <= 90:
            return "3mo"
        if lookback_days <= 180:
            return "6mo"
        if lookback_days <= 365:
            return "1y"
        if lookback_days <= 730:
            return "2y"
        if lookback_days <= 1825:
            return "5y"
        return "max"
