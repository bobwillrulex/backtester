from __future__ import annotations

import pandas as pd

from .base import BacktestResult

INDICATORS = {
    "fair_value_gap": "Fair Value Gap",
    "ema": "EMA",
    "rsi": "RSI",
    "stoch_rsi": "Stochastic RSI",
    "bb": "Bollinger Bands",
    "support_resistance": "Support / Resistance",
    "fibonacci": "Fibonacci Retracement",
    "vwap": "VWAP",
    "macd": "MACD",
    "volume": "Volume Surge",
    "ichimoku": "Ichimoku Cloud",
    "supply_demand": "Supply / Demand Zones",
}


def run_indicator_combo(
    candles: pd.DataFrame,
    selected_indicators: list[str],
    allow_multiple_positions: bool,
    hold_overnight: bool = True,
    stop_loss_mode: str = "none",
    stop_loss_percent: float = 2.0,
    trailing_stop: bool = False,
) -> BacktestResult:
    if not selected_indicators:
        raise ValueError("Select at least one indicator.")

    data = candles.copy()
    data["ret"] = data["close"].pct_change().fillna(0.0)
    stop_refs = _build_stop_reference_series(data)
    bullish_map: dict[str, pd.Series] = {}
    bearish_map: dict[str, pd.Series] = {}

    for indicator in selected_indicators:
        bullish_map[indicator], bearish_map[indicator] = _indicator_signals(data, indicator)

    bullish_all = pd.concat([bullish_map[i] for i in selected_indicators], axis=1).all(axis=1)
    bearish_any = pd.concat([bearish_map[i] for i in selected_indicators], axis=1).any(axis=1)

    open_positions = 0
    max_positions = 5 if allow_multiple_positions else 1
    equity = [1.0]
    trades = 0
    open_entries: list[dict[str, float | int | str | None]] = []
    closed_trades: list[dict[str, float | int | str]] = []
    last_flat_equity = 1.0

    def close_all_positions(*, exit_price: float, exit_time: str, exit_index: int, reason: str) -> None:
        nonlocal open_entries, open_positions
        for entry in open_entries:
            entry_price = float(entry["entry_price"])
            pnl_pct = ((exit_price / entry_price) - 1) * 100
            closed_trades.append(
                {
                    "entry_time": entry["entry_time"],
                    "exit_time": exit_time,
                    "entry_price": entry_price,
                    "exit_price": round(exit_price, 4),
                    "stop_loss": entry["stop_loss"] if entry["stop_loss"] is None else round(float(entry["stop_loss"]), 4),
                    "exit_reason": reason,
                    "pnl_pct": round(pnl_pct, 2),
                    "holding_candles": exit_index - int(entry["entry_index"]),
                }
            )

        open_positions = 0
        open_entries = []

    def stop_price_at_index(*, entry_price: float, i: int) -> float | None:
        if stop_loss_mode == "none":
            return None
        if stop_loss_mode == "percent":
            return entry_price * (1 - stop_loss_percent / 100)
        ref_series = stop_refs.get(stop_loss_mode)
        if ref_series is None:
            return None
        ref_value = ref_series.iloc[i]
        if pd.isna(ref_value):
            return None
        # Keep stop strictly below entry to avoid immediate invalidation.
        return min(float(ref_value), entry_price * 0.999)

    def try_stop_loss_exit(i: int) -> bool:
        nonlocal open_entries, open_positions
        if open_positions == 0:
            return False

        remaining: list[dict[str, float | int | str | None]] = []
        exited = False
        for entry in open_entries:
            candidate = stop_price_at_index(entry_price=float(entry["entry_price"]), i=i)
            if candidate is not None:
                if entry.get("stop_loss") is None:
                    entry["stop_loss"] = candidate
                elif trailing_stop:
                    entry["stop_loss"] = max(float(entry["stop_loss"]), candidate)
                else:
                    entry["stop_loss"] = candidate

            stop_value = entry.get("stop_loss")
            if stop_value is not None and float(data["low"].iloc[i]) <= float(stop_value):
                exit_price = min(float(data["close"].iloc[i]), float(stop_value))
                entry_price = float(entry["entry_price"])
                pnl_pct = ((exit_price / entry_price) - 1) * 100
                closed_trades.append(
                    {
                        "entry_time": entry["entry_time"],
                        "exit_time": _format_trade_time(data.index[i]),
                        "entry_price": entry_price,
                        "exit_price": round(exit_price, 4),
                        "stop_loss": round(float(stop_value), 4),
                        "exit_reason": "stop_loss",
                        "pnl_pct": round(pnl_pct, 2),
                        "holding_candles": i - int(entry["entry_index"]),
                    }
                )
                open_positions -= 1
                exited = True
            else:
                remaining.append(entry)

        open_entries = remaining
        return exited

    for i in range(1, len(data)):
        # Returns from close[i-1] -> close[i] belong to the position state carried into candle i.
        # Signals on candle i are acted on at candle i close and only affect subsequent bars.
        leverage = open_positions if allow_multiple_positions else min(open_positions, 1)
        current = equity[-1] * (1 + leverage * data["ret"].iloc[i])
        equity.append(max(current, 0.0))

        if not hold_overnight and open_positions > 0 and data.index[i].date() != data.index[i - 1].date():
            close_all_positions(
                exit_price=float(data["close"].iloc[i - 1]),
                exit_time=_format_trade_time(data.index[i - 1]),
                exit_index=i - 1,
                reason="day_close",
            )

        try_stop_loss_exit(i)

        if bearish_any.iloc[i] and open_positions > 0:
            close_all_positions(
                exit_price=float(data["close"].iloc[i]),
                exit_time=_format_trade_time(data.index[i]),
                exit_index=i,
                reason="signal_exit",
            )

        if bullish_all.iloc[i] and open_positions < max_positions:
            open_positions += 1
            trades += 1
            open_entries.append(
                {
                    "entry_index": i,
                    "entry_time": _format_trade_time(data.index[i]),
                    "entry_price": round(float(data["close"].iloc[i]), 4),
                    "stop_loss": stop_price_at_index(entry_price=float(data["close"].iloc[i]), i=i),
                }
            )

        if open_positions == 0:
            last_flat_equity = equity[-1]

    equity_curve = pd.Series(equity, index=data.index)
    total_return_pct = (equity_curve.iloc[-1] - 1) * 100
    previous_return_pct = (last_flat_equity - 1) * 100

    final_close = float(data["close"].iloc[-1])
    liquidated_equity = equity_curve.iloc[-1]
    if open_entries:
        liquidated_equity = 0.0
        for entry in open_entries:
            entry_price = float(entry["entry_price"])
            liquidated_equity += final_close / entry_price
    liquidated_return_pct = (liquidated_equity - 1) * 100

    notes = (
        "Entry requires all selected indicators to be bullish at the same candle. "
        "Exit happens when any selected indicator turns bearish."
    )
    if not hold_overnight:
        notes += " Open trades are also closed at each day boundary to avoid overnight holds."
    if stop_loss_mode != "none":
        notes += f" Stop loss mode: {stop_loss_mode}."
        if stop_loss_mode == "percent":
            notes += f" Percent stop: {stop_loss_percent:.2f}%."
        if trailing_stop:
            notes += " Trailing stop is enabled."
    gains = [float(t["pnl_pct"]) for t in closed_trades]
    winning = [g for g in gains if g > 0]
    win_rate_pct = (len(winning) / len(gains) * 100) if gains else 0.0
    average_gain_pct = (sum(gains) / len(gains)) if gains else 0.0

    return BacktestResult(
        total_return_pct=round(float(total_return_pct), 2),
        previous_return_pct=round(float(previous_return_pct), 2),
        liquidated_return_pct=round(float(liquidated_return_pct), 2),
        trades=trades,
        equity_curve=equity_curve,
        notes=notes,
        win_rate_pct=round(win_rate_pct, 2),
        average_gain_pct=round(average_gain_pct, 2),
        trade_details=closed_trades,
    )


def _indicator_signals(data: pd.DataFrame, indicator: str) -> tuple[pd.Series, pd.Series]:
    close = data["close"]
    high = data["high"]
    low = data["low"]
    volume = data["volume"].replace(0, pd.NA).ffill().fillna(1.0)

    if indicator == "fair_value_gap":
        bullish = low > high.shift(2)
        bearish = high < low.shift(2)
    elif indicator == "ema":
        ema_fast = close.ewm(span=12, adjust=False).mean()
        ema_slow = close.ewm(span=26, adjust=False).mean()
        bullish = ema_fast > ema_slow
        bearish = ema_fast < ema_slow
    elif indicator == "rsi":
        rsi = _rsi(close)
        bullish = rsi < 35
        bearish = rsi > 70
    elif indicator == "stoch_rsi":
        rsi = _rsi(close)
        stoch = (rsi - rsi.rolling(14).min()) / (rsi.rolling(14).max() - rsi.rolling(14).min())
        bullish = stoch < 0.2
        bearish = stoch > 0.8
    elif indicator == "bb":
        mid = close.rolling(20).mean()
        std = close.rolling(20).std()
        lower = mid - (2 * std)
        upper = mid + (2 * std)
        bullish = close < lower
        bearish = close > upper
    elif indicator == "support_resistance":
        support = low.rolling(30).quantile(0.2)
        resistance = high.rolling(30).quantile(0.8)
        tolerance = 0.0075

        support_touch = (low <= support * (1 + tolerance)) & (close >= support * (1 - tolerance))
        resistance_touch = (high >= resistance * (1 - tolerance)) & (close <= resistance * (1 + tolerance))
        support_touches = support_touch.rolling(30, min_periods=1).sum()
        resistance_touches = resistance_touch.rolling(30, min_periods=1).sum()

        bounce = support_touch & (close > close.shift(1))
        breakout = close > resistance * (1 + tolerance)
        breakdown = close < support * (1 - tolerance)

        bullish = ((support_touches >= 2) & bounce) | breakout
        bearish = ((resistance_touches >= 2) & resistance_touch & (close < close.shift(1))) | breakdown
    elif indicator == "fibonacci":
        swing_high = high.rolling(50).max()
        swing_low = low.rolling(50).min()
        fib_618 = swing_high - (swing_high - swing_low) * 0.618
        fib_382 = swing_high - (swing_high - swing_low) * 0.382
        bullish = close <= fib_618
        bearish = close >= fib_382
    elif indicator == "vwap":
        typical = (high + low + close) / 3
        cum_vp = (typical * volume).cumsum()
        cum_vol = volume.cumsum()
        vwap = cum_vp / cum_vol
        bullish = close > vwap
        bearish = close < vwap
    elif indicator == "macd":
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        bullish = macd > signal
        bearish = macd < signal
    elif indicator == "volume":
        vol_ma = volume.rolling(20).mean()
        bullish = volume > vol_ma * 1.5
        bearish = volume < vol_ma * 0.8
    elif indicator == "ichimoku":
        conv = (high.rolling(9).max() + low.rolling(9).min()) / 2
        base = (high.rolling(26).max() + low.rolling(26).min()) / 2
        span_a = ((conv + base) / 2).shift(26)
        span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
        cloud_top = pd.concat([span_a, span_b], axis=1).max(axis=1)
        cloud_bottom = pd.concat([span_a, span_b], axis=1).min(axis=1)
        bullish = close > cloud_top
        bearish = close < cloud_bottom
    elif indicator == "supply_demand":
        demand = low.rolling(30).quantile(0.15)
        supply = high.rolling(30).quantile(0.85)
        bullish = close <= demand * 1.01
        bearish = close >= supply * 0.99
    else:
        raise ValueError(f"Unknown indicator: {indicator}")

    return bullish.fillna(False), bearish.fillna(False)


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    return (100 - (100 / (1 + rs))).fillna(50)


def _build_stop_reference_series(data: pd.DataFrame) -> dict[str, pd.Series]:
    close = data["close"]
    high = data["high"]
    low = data["low"]
    volume = data["volume"].replace(0, pd.NA).ffill().fillna(1.0)

    ema_slow = close.ewm(span=26, adjust=False).mean()

    typical = (high + low + close) / 3
    vwap = (typical * volume).cumsum() / volume.cumsum()

    support = low.rolling(30).quantile(0.2)

    conv = (high.rolling(9).max() + low.rolling(9).min()) / 2
    base = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = ((conv + base) / 2).shift(26)
    span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    ichimoku_floor = pd.concat([span_a, span_b, base], axis=1).min(axis=1)

    return {
        "support_resistance": support,
        "ichimoku": ichimoku_floor,
        "vwap": vwap,
        "ema": ema_slow,
    }


def _format_trade_time(ts: pd.Timestamp) -> str:
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert(None)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S")
