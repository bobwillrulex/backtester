from __future__ import annotations

import pandas as pd

from .base import BacktestResult, Strategy


class FairValueGapStrategy(Strategy):
    name = "fair_value_gap"

    def run(self, candles: pd.DataFrame, allow_multiple_positions: bool) -> BacktestResult:
        data = candles.copy()
        data["ret"] = data["close"].pct_change().fillna(0.0)

        bullish_fvg = data["low"] > data["high"].shift(2)
        bearish_fvg = data["high"] < data["low"].shift(2)

        open_positions = 0
        max_positions = 5 if allow_multiple_positions else 1
        equity = [1.0]
        trades = 0

        for i in range(1, len(data)):
            if bullish_fvg.iloc[i] and open_positions < max_positions:
                open_positions += 1
                trades += 1

            if bearish_fvg.iloc[i] and open_positions > 0:
                open_positions = 0

            leverage = open_positions if allow_multiple_positions else min(open_positions, 1)
            current = equity[-1] * (1 + leverage * data["ret"].iloc[i])
            equity.append(max(current, 0.0))

        equity_curve = pd.Series(equity, index=data.index)
        total_return_pct = (equity_curve.iloc[-1] - 1) * 100

        notes = (
            "Bullish FVG opens a long position when candle low is above the high from two candles back. "
            "Bearish FVG (candle high below low from two candles back) closes all positions."
        )

        return BacktestResult(
            total_return_pct=round(float(total_return_pct), 2),
            trades=trades,
            equity_curve=equity_curve,
            notes=notes,
        )
