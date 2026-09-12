"""Performance metrics computed from a backtest.engine.BacktestResult."""
import numpy as np
import pandas as pd


def max_drawdown_pct(equity_curve: pd.Series) -> float:
    peak = equity_curve.cummax()
    drawdown = (peak - equity_curve) / peak
    return float(drawdown.max())


def cagr(equity_curve: pd.Series) -> float:
    if len(equity_curve) < 2:
        return 0.0
    start, end = equity_curve.iloc[0], equity_curve.iloc[-1]
    years = (equity_curve.index[-1] - equity_curve.index[0]).days / 365.25
    if years <= 0 or start <= 0:
        return 0.0
    return float((end / start) ** (1 / years) - 1)


def sharpe_ratio(equity_curve: pd.Series, periods_per_year: int = 252) -> float:
    """Computed on daily-resampled returns to smooth out intraday bar noise."""
    daily = equity_curve.resample("1D").last().dropna()
    returns = daily.pct_change().dropna()
    if returns.std() == 0 or len(returns) < 2:
        return 0.0
    return float(returns.mean() / returns.std() * np.sqrt(periods_per_year))


def summarize(result, starting_equity: float) -> dict:
    equity = result.equity_curve["equity"]
    fills = result.fills_df()

    round_trips = fills[fills["realized_pnl"].notna()] if not fills.empty else fills
    wins = round_trips[round_trips["realized_pnl"] > 0] if not round_trips.empty else round_trips
    losses = round_trips[round_trips["realized_pnl"] <= 0] if not round_trips.empty else round_trips

    total_commission = float(fills["commission"].sum()) if not fills.empty else 0.0
    gross_win = float(wins["realized_pnl"].sum()) if not wins.empty else 0.0
    gross_loss = float(losses["realized_pnl"].sum()) if not losses.empty else 0.0

    summary = {
        "starting_equity": starting_equity,
        "ending_equity": float(equity.iloc[-1]) if len(equity) else starting_equity,
        "total_return_pct": (float(equity.iloc[-1]) / starting_equity - 1) if len(equity) else 0.0,
        "cagr": cagr(equity),
        "max_drawdown_pct": max_drawdown_pct(equity) if len(equity) else 0.0,
        "sharpe_ratio": sharpe_ratio(equity) if len(equity) else 0.0,
        "num_round_trips": int(len(round_trips)),
        "win_rate": float(len(wins) / len(round_trips)) if len(round_trips) else 0.0,
        "avg_win": float(wins["realized_pnl"].mean()) if not wins.empty else 0.0,
        "avg_loss": float(losses["realized_pnl"].mean()) if not losses.empty else 0.0,
        "profit_factor": float(gross_win / abs(gross_loss)) if gross_loss < 0 else float("inf") if gross_win > 0 else 0.0,
        "total_commission_paid": total_commission,
        "halted_by_circuit_breaker": result.halted_at is not None,
        "halted_at": str(result.halted_at) if result.halted_at is not None else None,
    }

    if not round_trips.empty:
        summary["pnl_by_symbol"] = round_trips.groupby("symbol")["realized_pnl"].sum().to_dict()
        summary["pnl_by_strategy"] = round_trips.groupby("strategy")["realized_pnl"].sum().to_dict()

    return summary


def print_summary(summary: dict) -> None:
    print("\n=== Backtest summary ===")
    print(f"Starting equity:      ${summary['starting_equity']:,.2f}")
    print(f"Ending equity:        ${summary['ending_equity']:,.2f}")
    print(f"Total return:         {summary['total_return_pct']:.2%}")
    print(f"CAGR:                 {summary['cagr']:.2%}")
    print(f"Max drawdown:         {summary['max_drawdown_pct']:.2%}")
    print(f"Sharpe ratio:         {summary['sharpe_ratio']:.2f}")
    print(f"Round trips:          {summary['num_round_trips']}")
    print(f"Win rate:             {summary['win_rate']:.2%}")
    print(f"Avg win / avg loss:   ${summary['avg_win']:,.2f} / ${summary['avg_loss']:,.2f}")
    print(f"Profit factor:        {summary['profit_factor']:.2f}")
    print(f"Total commission:     ${summary['total_commission_paid']:,.2f}")
    if summary["halted_by_circuit_breaker"]:
        print(f"CIRCUIT BREAKER FIRED at {summary['halted_at']}")
    if "pnl_by_symbol" in summary:
        print("PnL by symbol:       ", summary["pnl_by_symbol"])
        print("PnL by strategy:     ", summary["pnl_by_strategy"])
