# Flask Backtester (Alpha Vantage + Yahoo Finance)

A simple Flask backtester with:

- Data provider toggle (Alpha Vantage or Yahoo Finance)
- Intraday candles via Yahoo Finance (1/5/15/30/60 min + 1 hr alias)
- Daily/weekly/monthly candles via both providers
- Lookback period in days (e.g. 365 for 1 year)
- Request tracking for Alpha Vantage's 25-request/day free tier
- Single-position or multi-position mode
- Trade category selector (no category/hold overnight or day trades only)
- Multi-indicator strategy builder using checkboxes
- Included indicators: Fair Value Gap, EMA, RSI, Stoch RSI, Bollinger Bands, Support/Resistance, Fibonacci, VWAP, MACD, Volume, Ichimoku Cloud, Supply/Demand zones

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000`.

## Notes

- Fees are modeled as 0.
- Bid/ask spread is not included.
- Multi-position mode allows stacking up to 5 concurrent long positions.
- Combo logic: all selected indicators must be bullish to enter; any selected bearish signal exits.
- Return reporting includes current equity, previous flat-equity checkpoint, and end-of-backtest liquidated equity
