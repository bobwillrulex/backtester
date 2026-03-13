from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd


@dataclass(slots=True)
class BacktestResult:
    total_return_pct: float
    trades: int
    equity_curve: pd.Series
    notes: str
    win_rate_pct: float = 0.0
    average_gain_pct: float = 0.0
    trade_details: list[dict[str, str | float | int]] = field(default_factory=list)


class Strategy(ABC):
    name: str

    @abstractmethod
    def run(self, candles: pd.DataFrame, allow_multiple_positions: bool) -> BacktestResult:
        raise NotImplementedError
