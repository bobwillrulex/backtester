from __future__ import annotations

from flask import Flask, render_template, request

from backtester.data_clients import (
    AlphaVantageClient,
    CandleRequest,
    DataClientError,
    YahooFinanceClient,
)
from backtester.strategies.indicator_combo import INDICATORS, run_indicator_combo

DEFAULT_API_KEY = "5OTAZMSKH3K8A5KI"

app = Flask(__name__)
alpha_client = AlphaVantageClient(api_key=DEFAULT_API_KEY)
yahoo_client = YahooFinanceClient()

INTERVAL_OPTIONS = {
    "alpha": {
        "daily": ["1day"],
        "weekly": ["1week"],
        "monthly": ["1month"],
    },
    "yahoo": {
        "intraday": ["1min", "5min", "15min", "30min", "60min"],
        "daily": ["1day"],
        "weekly": ["1week"],
        "monthly": ["1month"],
    },
}


def render_home(*, result=None, error=None, api_key=DEFAULT_API_KEY, requests_remaining=None):
    return render_template(
        "index.html",
        interval_options=INTERVAL_OPTIONS,
        indicator_options=INDICATORS,
        default_api_key=api_key,
        requests_remaining=alpha_client.get_requests_remaining() if requests_remaining is None else requests_remaining,
        result=result,
        error=error,
    )


@app.get("/")
def index():
    return render_home()


@app.post("/backtest")
def run_backtest():
    ticker = request.form.get("ticker", "").strip().upper()
    provider = request.form.get("provider", "alpha")
    data_mode = request.form.get("data_mode", "daily")
    interval = request.form.get("interval", "1day")
    lookback_days = int(request.form.get("lookback_days", "365"))
    selected_indicators = request.form.getlist("indicators")
    position_mode = request.form.get("position_mode", "single")
    api_key = request.form.get("api_key", "").strip() or DEFAULT_API_KEY

    local_alpha_client = AlphaVantageClient(api_key=api_key)
    local_alpha_client.requests_made = alpha_client.requests_made

    try:
        if not ticker:
            raise ValueError("Ticker is required.")
        if provider not in INTERVAL_OPTIONS:
            raise ValueError("Invalid data provider selected.")
        if data_mode not in INTERVAL_OPTIONS[provider]:
            raise ValueError(f"{provider.title()} does not support {data_mode} mode.")
        if interval not in INTERVAL_OPTIONS[provider][data_mode]:
            raise ValueError("Invalid candle interval for selected provider/mode.")

        req = CandleRequest(
            symbol=ticker,
            provider=provider,
            mode=data_mode,
            interval=interval,
            lookback_days=lookback_days,
        )
        if provider == "alpha":
            candles = local_alpha_client.fetch_candles(req)
            alpha_client.requests_made = local_alpha_client.requests_made
            requests_remaining = alpha_client.get_requests_remaining()
        else:
            candles = yahoo_client.fetch_candles(req)
            requests_remaining = alpha_client.get_requests_remaining()

        result = run_indicator_combo(
            candles,
            selected_indicators=selected_indicators,
            allow_multiple_positions=(position_mode == "multi"),
        )

        return render_home(
            api_key=api_key,
            requests_remaining=requests_remaining,
            result={
                "ticker": ticker,
                "provider": provider,
                "candles": len(candles),
                "return_pct": result.total_return_pct,
                "trades": result.trades,
                "notes": result.notes,
                "indicators": [INDICATORS[i] for i in selected_indicators],
            },
        )
    except (ValueError, DataClientError) as exc:
        app.logger.exception("Backtest request failed: %s", exc)
        return render_home(
            api_key=api_key,
            requests_remaining=local_alpha_client.get_requests_remaining(),
            error=str(exc),
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
