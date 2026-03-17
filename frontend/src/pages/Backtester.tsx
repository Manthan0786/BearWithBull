import { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const API_BASE = "";

const STRATEGIES = [
  { id: "momentum_breakout", name: "Momentum Breakout" },
  { id: "stat_mean_reversion", name: "Stat Mean Reversion" },
  { id: "sentiment_catalyst", name: "Sentiment Catalyst" },
];

export type BacktestResult = {
  equityCurve: { date: string; value: number }[];
  maxDrawdown: number;
  sharpe: number;
  sortino: number;
  winRate: number;
  profitFactor: number;
  totalReturnPct: number;
  avgTradePnl: number;
  bestTrade: number;
  worstTrade: number;
  totalTrades: number;
  trades: { ticker: string; entry: string; exit: string; pnl: number; direction?: string; exit_reason?: string }[];
};

export function Backtester() {
  const [strategyId, setStrategyId] = useState("momentum_breakout");
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState("2024-12-31");
  const [startingCapital, setStartingCapital] = useState(100000);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);

  const runBacktest = async () => {
    setRunning(true);
    setResult(null);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/backtest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          strategyId,
          startDate,
          endDate,
          startingCapital,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail?.toString() || res.statusText || "Backtest failed");
        return;
      }
      setResult({
        equityCurve: data.equityCurve ?? [],
        maxDrawdown: data.maxDrawdown ?? 0,
        sharpe: data.sharpe ?? 0,
        sortino: data.sortino ?? 0,
        winRate: data.winRate ?? 0,
        profitFactor: data.profitFactor ?? 0,
        totalReturnPct: data.totalReturnPct ?? 0,
        avgTradePnl: data.avgTradePnl ?? 0,
        bestTrade: data.bestTrade ?? 0,
        worstTrade: data.worstTrade ?? 0,
        totalTrades: data.totalTrades ?? 0,
        trades: (data.trades ?? []).map((t: { ticker: string; entry: string; exit: string; pnl: number; direction?: string; exit_reason?: string }) => ({
          ticker: t.ticker,
          entry: t.entry,
          exit: t.exit,
          pnl: t.pnl,
          direction: t.direction,
          exit_reason: t.exit_reason,
        })),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      <h1 className="text-2xl font-semibold text-zinc-100">Backtester</h1>

      {error && (
        <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-3 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Inputs */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Strategy</label>
            <select
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
            >
              {STRATEGIES.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Start date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">End date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Starting capital (USD)</label>
            <input
              type="number"
              value={startingCapital}
              onChange={(e) => setStartingCapital(Number(e.target.value))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={runBacktest}
              disabled={running}
              className="w-full px-4 py-2 rounded font-medium bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white"
            >
              {running ? "Running…" : "Run backtest"}
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      {result && (
        <>
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
            <h2 className="text-sm font-medium text-zinc-400 mb-4">Equity curve</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={result.equityCurve} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis dataKey="date" stroke="#71717a" fontSize={12} />
                  <YAxis stroke="#71717a" fontSize={12} tickFormatter={(v) => `$${Number(v).toLocaleString()}`} />
                  <Tooltip contentStyle={{ backgroundColor: "#18181b", border: "1px solid #27272a" }} formatter={(v: number) => [`$${Number(v).toLocaleString()}`, "Equity"]} />
                  <Line type="monotone" dataKey="value" stroke="#22c55e" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <StatBox label="Total trades" value={String(result.totalTrades)} />
            <StatBox label="Max drawdown" value={`${result.maxDrawdown}%`} />
            <StatBox label="Sharpe" value={result.sharpe.toFixed(2)} />
            <StatBox label="Sortino" value={result.sortino.toFixed(2)} />
            <StatBox label="Win rate" value={`${(result.winRate * 100).toFixed(1)}%`} />
            <StatBox label="Profit factor" value={result.profitFactor.toFixed(2)} />
            <StatBox label="Total return" value={`${result.totalReturnPct}%`} positive={result.totalReturnPct >= 0} />
            <StatBox label="Avg trade P&L" value={`$${result.avgTradePnl.toFixed(2)}`} positive={result.avgTradePnl >= 0} />
            <StatBox label="Best trade" value={`$${result.bestTrade.toFixed(2)}`} positive />
            <StatBox label="Worst trade" value={`$${result.worstTrade.toFixed(2)}`} positive={false} />
          </div>

          {result.trades.length > 0 ? (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 overflow-hidden">
              <h2 className="text-sm font-medium text-zinc-400 px-4 py-3 border-b border-zinc-800">Trades ({result.trades.length})</h2>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-zinc-500 border-b border-zinc-800">
                    <th className="px-4 py-2">Ticker</th>
                    <th className="px-4 py-2">Direction</th>
                    <th className="px-4 py-2">Entry</th>
                    <th className="px-4 py-2">Exit</th>
                    <th className="px-4 py-2">P&L</th>
                    <th className="px-4 py-2">Exit reason</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, i) => (
                    <tr key={i} className="border-b border-zinc-800/50">
                      <td className="px-4 py-2 font-mono">{t.ticker}</td>
                      <td className="px-4 py-2">{t.direction ?? "–"}</td>
                      <td className="px-4 py-2">{t.entry}</td>
                      <td className="px-4 py-2">{t.exit}</td>
                      <td className={t.pnl >= 0 ? "text-emerald-400" : "text-red-400"}>${t.pnl.toFixed(2)}</td>
                      <td className="px-4 py-2 text-zinc-500">{t.exit_reason ?? "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-zinc-500 text-sm">
              No trades in this period. Try a different date range or ensure daily data is loaded for the watchlist (run the app with IB connected to bootstrap historical data).
            </div>
          )}
        </>
      )}
    </div>
  );
}

function StatBox({
  label,
  value,
  positive,
}: {
  label: string;
  value: string;
  positive?: boolean;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
      <p className="text-xs text-zinc-500">{label}</p>
      <p
        className={
          positive === true ? "text-emerald-400 font-mono" : positive === false ? "text-red-400 font-mono" : "text-zinc-200 font-mono"
        }
      >
        {value}
      </p>
    </div>
  );
}
