from __future__ import annotations

from flask import Flask, render_template, request

from backtester.alpha_vantage_client import AlphaVantageClient, AlphaVantageError, CandleRequest
from backtester.strategies.registry import get_strategy, list_strategies

DEFAULT_API_KEY = "5OTAZMSKH3K8A5KI"

app = Flask(__name__)
client = AlphaVantageClient(api_key=DEFAULT_API_KEY)

INTERVAL_OPTIONS = {
    "intraday": ["1min", "5min", "15min", "30min", "60min"],
    "daily": ["1day"],
    "weekly": ["1week"],
    "monthly": ["1month"],
}


@app.get("/")
def index():
    return render_template(
        "index.html",
        interval_options=INTERVAL_OPTIONS,
        strategies=list_strategies(),
        default_api_key=DEFAULT_API_KEY,
        requests_remaining=client.get_requests_remaining(),
        result=None,
        error=None,
    )


@app.post("/backtest")
def run_backtest():
    ticker = request.form.get("ticker", "").strip().upper()
    data_mode = request.form.get("data_mode", "daily")
    interval = request.form.get("interval", "1day")
    lookback_days = int(request.form.get("lookback_days", "365"))
    strategy_name = request.form.get("strategy", "fair_value_gap")
    position_mode = request.form.get("position_mode", "single")
    api_key = request.form.get("api_key", "").strip() or DEFAULT_API_KEY

    local_client = AlphaVantageClient(api_key=api_key)
    local_client.requests_made = client.requests_made

    try:
        if not ticker:
            raise ValueError("Ticker is required.")
        req = CandleRequest(
            symbol=ticker,
            mode=data_mode,
            interval=interval if data_mode == "intraday" else None,
            lookback_days=lookback_days,
        )
        candles = local_client.fetch_candles(req)
        strategy = get_strategy(strategy_name)
        result = strategy.run(candles, allow_multiple_positions=(position_mode == "multi"))

        client.requests_made = local_client.requests_made

        return render_template(
            "index.html",
            interval_options=INTERVAL_OPTIONS,
            strategies=list_strategies(),
            default_api_key=api_key,
            requests_remaining=client.get_requests_remaining(),
            result={
                "ticker": ticker,
                "candles": len(candles),
                "return_pct": result.total_return_pct,
                "trades": result.trades,
                "notes": result.notes,
            },
            error=None,
        )
    except (ValueError, AlphaVantageError) as exc:
        return render_template(
            "index.html",
            interval_options=INTERVAL_OPTIONS,
            strategies=list_strategies(),
            default_api_key=api_key,
            requests_remaining=local_client.get_requests_remaining(),
            result=None,
            error=str(exc),
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
