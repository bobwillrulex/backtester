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
        "intraday": ["1min", "5min", "15min", "30min", "60min", "1hr"],
        "daily": ["1day"],
        "weekly": ["1week"],
        "monthly": ["1month"],
    },
}


def render_home(*, result=None, error=None, api_key=DEFAULT_API_KEY, requests_remaining=None, form_data=None):
    form_data = form_data or {
        "provider": "alpha",
        "data_mode": "daily",
        "interval": "1day",
        "ticker": "",
        "lookback_days": 365,
        "position_mode": "single",
        "trade_category": "none",
        "indicators": ["fair_value_gap"],
        "stop_loss_mode": "none",
        "stop_loss_percent": 2.0,
        "trailing_stop": False,
    }
    return render_template(
        "index.html",
        interval_options=INTERVAL_OPTIONS,
        indicator_options=INDICATORS,
        default_api_key=api_key,
        requests_remaining=alpha_client.get_requests_remaining() if requests_remaining is None else requests_remaining,
        result=result,
        error=error,
        form_data=form_data,
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
    trade_category = request.form.get("trade_category", "none")
    api_key = request.form.get("api_key", "").strip() or DEFAULT_API_KEY
    stop_loss_mode = request.form.get("stop_loss_mode", "none")
    stop_loss_percent = float(request.form.get("stop_loss_percent", "2") or "2")
    trailing_stop = request.form.get("trailing_stop") == "on"
    form_data = {
        "provider": provider,
        "data_mode": data_mode,
        "interval": interval,
        "ticker": ticker,
        "lookback_days": lookback_days,
        "position_mode": position_mode,
        "trade_category": trade_category,
        "indicators": selected_indicators,
        "stop_loss_mode": stop_loss_mode,
        "stop_loss_percent": stop_loss_percent,
        "trailing_stop": trailing_stop,
    }

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
        if trade_category not in {"none", "day"}:
            raise ValueError("Invalid trade category selected.")
        if stop_loss_mode not in {"none", "percent", "support_resistance", "ichimoku", "vwap", "ema"}:
            raise ValueError("Invalid stop-loss mode selected.")
        if stop_loss_percent <= 0 or stop_loss_percent >= 100:
            raise ValueError("Stop-loss percent must be between 0 and 100.")

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
            hold_overnight=(trade_category == "none"),
            stop_loss_mode=stop_loss_mode,
            stop_loss_percent=stop_loss_percent,
            trailing_stop=trailing_stop,
        )

        return render_home(
            api_key=api_key,
            requests_remaining=requests_remaining,
            form_data=form_data,
            result={
                "ticker": ticker,
                "provider": provider,
                "candles": len(candles),
                "return_pct": result.total_return_pct,
                "previous_return_pct": result.previous_return_pct,
                "liquidated_return_pct": result.liquidated_return_pct,
                "trades": result.trades,
                "win_rate_pct": result.win_rate_pct,
                "average_gain_pct": result.average_gain_pct,
                "notes": result.notes,
                "indicators": [INDICATORS[i] for i in selected_indicators],
                "stop_loss_mode": stop_loss_mode,
                "stop_loss_percent": round(stop_loss_percent, 2),
                "trailing_stop": trailing_stop,
                "trade_details": result.trade_details,
            },
        )
    except (ValueError, DataClientError) as exc:
        app.logger.exception("Backtest request failed: %s", exc)
        return render_home(
            api_key=api_key,
            requests_remaining=local_alpha_client.get_requests_remaining(),
            error=str(exc),
            form_data=form_data,
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
