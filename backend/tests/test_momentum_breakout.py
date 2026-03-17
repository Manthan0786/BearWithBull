from datetime import datetime

import pandas as pd

from backend.strategies.momentum_breakout import MomentumBreakout


def test_momentum_breakout_long_signal():
    strat = MomentumBreakout()
    now = datetime.utcnow()

    df = pd.DataFrame(
        [
            {
                "time": now,
                "close": 105.0,
                "volume": 2_000_000,
                "sma50": 100.0,
                "rsi14": 60.0,
                "rolling_high_20": 104.0,
                "rolling_low_20": 90.0,
                "vol_sma20": 1_000_000,
                "atr14": 2.0,
                "mom_20d": 0.1,
                "rs_spy_20d": 0.05,
            }
        ]
    ).set_index("time")

    signals = strat.generate_signals({"AAPL": df})
    # single symbol is in top 20% and satisfies long conditions
    assert len(signals) == 1
    sig = signals[0]
    assert sig.ticker == "AAPL"
    assert sig.direction == "LONG"

