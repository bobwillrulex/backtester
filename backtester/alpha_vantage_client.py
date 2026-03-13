from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Literal

import pandas as pd
import requests


class AlphaVantageError(RuntimeError):
    pass


DataMode = Literal["intraday", "daily", "weekly", "monthly"]


@dataclass(slots=True)
class CandleRequest:
    symbol: str
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
        params: dict[str, str] = {
            "apikey": self.api_key,
            "symbol": req.symbol.upper(),
        }

        if req.mode == "intraday":
            if not req.interval:
                raise AlphaVantageError("Intraday mode requires an interval.")
            params.update(
                {
                    "function": "TIME_SERIES_INTRADAY",
                    "interval": req.interval,
                    "outputsize": "full",
                    "datatype": "json",
                }
            )
            key = f"Time Series ({req.interval})"
        elif req.mode == "daily":
            params.update(
                {
                    "function": "TIME_SERIES_DAILY_ADJUSTED",
                    "outputsize": "full",
                    "datatype": "json",
                }
            )
            key = "Time Series (Daily)"
        elif req.mode == "weekly":
            params.update({"function": "TIME_SERIES_WEEKLY", "datatype": "json"})
            key = "Weekly Time Series"
        elif req.mode == "monthly":
            params.update({"function": "TIME_SERIES_MONTHLY", "datatype": "json"})
            key = "Monthly Time Series"
        else:
            raise AlphaVantageError(f"Unsupported data mode: {req.mode}")

        response = requests.get(self.BASE_URL, params=params, timeout=30)
        self.requests_made += 1
        response.raise_for_status()
        payload = response.json()

        if "Note" in payload:
            raise AlphaVantageError(payload["Note"])
        if "Error Message" in payload:
            raise AlphaVantageError(payload["Error Message"])
        if key not in payload:
            serialized_payload = json.dumps(payload, ensure_ascii=False)
            raise AlphaVantageError(
                "Alpha Vantage did not return expected candle data. "
                f"Expected key '{key}'. Full response: {serialized_payload}"
            )

        raw = payload[key]
        frame = (
            pd.DataFrame.from_dict(raw, orient="index")
            .rename(
                columns={
                    "1. open": "open",
                    "2. high": "high",
                    "3. low": "low",
                    "4. close": "close",
                    "5. volume": "volume",
                    "5. adjusted close": "adjusted_close",
                    "6. volume": "volume",
                }
            )
            .astype(float, errors="ignore")
        )
        frame.index = pd.to_datetime(frame.index, utc=True)
        frame = frame.sort_index()

        cutoff = datetime.now(timezone.utc) - timedelta(days=req.lookback_days)
        frame = frame[frame.index >= cutoff]
        if frame.empty:
            raise AlphaVantageError("No candles available for requested lookback period.")
        return frame[["open", "high", "low", "close"]]
