# Alpha Vantage GUI Backtester

A simple Flask backtester with:

- Ticker input (e.g. NVDA)
- Candle type + interval dropdowns based on Alpha Vantage options
- Lookback period in days (e.g. 365 for 1 year)
- Request tracking for Alpha Vantage's 25-request/day free tier
- Single-position or multi-position mode
- Strategy registry design for easy strategy add/remove/edit
- Fair Value Gap strategy included

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
