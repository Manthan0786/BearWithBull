from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class StrategyConfig(BaseModel):
  enabled: bool = True
  risk_per_trade_pct: float
  max_concurrent: int
  vix_threshold: float | None = None
  sentiment_threshold: float | None = None
  max_hold_minutes: int | None = None


class TradingConfig(BaseModel):
  paper_mode: bool = True
  allow_overnight: bool = False
  max_positions: int = 10
  cash_reserve_pct: float = 0.20
  daily_loss_limit_pct: float = 0.03
  max_daily_trades: int = 20
  consecutive_loss_circuit_breaker: int = 4
  circuit_breaker_pause_minutes: int = 120


class AppConfig(BaseModel):
  trading: TradingConfig
  strategies: dict[str, StrategyConfig]
  watchlist: list[str]


def load_config(path: str | Path = "config.yaml") -> AppConfig:
  data: dict[str, Any] = yaml.safe_load(Path(path).read_text())
  strategies: dict[str, StrategyConfig] = {}
  for name, cfg in data.get("strategies", {}).items():
    strategies[name] = StrategyConfig(**cfg)

  return AppConfig(
    trading=TradingConfig(**data.get("trading", {})),
    strategies=strategies,
    watchlist=data.get("watchlist", []),
  )

