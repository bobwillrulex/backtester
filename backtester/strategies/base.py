from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class BacktestResult:
    total_return_pct: float
    trades: int
    equity_curve: pd.Series
    notes: str


class Strategy(ABC):
    name: str

    @abstractmethod
    def run(self, candles: pd.DataFrame, allow_multiple_positions: bool) -> BacktestResult:
        raise NotImplementedError
