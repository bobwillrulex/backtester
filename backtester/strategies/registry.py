from __future__ import annotations

from .base import Strategy
from .fair_value_gap import FairValueGapStrategy


def get_strategy(name: str) -> Strategy:
    strategies: dict[str, Strategy] = {
        FairValueGapStrategy.name: FairValueGapStrategy(),
    }
    if name not in strategies:
        raise ValueError(f"Unknown strategy: {name}")
    return strategies[name]


def list_strategies() -> list[str]:
    return [FairValueGapStrategy.name]
