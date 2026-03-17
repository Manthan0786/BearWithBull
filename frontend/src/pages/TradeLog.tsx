import { useState } from "react";
import { useAppStore } from "../store/useAppStore";
import type { TradeLogEntry } from "../types";

export function TradeLog() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [strategyFilter, setStrategyFilter] = useState("");
  const [tickerFilter, setTickerFilter] = useState("");

  const trades = useAppStore((s) => s.tradeLog);

  const filtered = trades.filter((t) => {
    if (dateFrom && t.date < dateFrom) return false;
    if (dateTo && t.date > dateTo) return false;
    if (strategyFilter && t.strategy !== strategyFilter) return false;
    if (tickerFilter && t.ticker !== tickerFilter) return false;
    return true;
  });

  const exportCsv = () => {
    const headers = ["Date", "Ticker", "Strategy", "Direction", "Entry", "Exit", "P&L", "P&L%", "Hold", "Exit reason", "Slippage bps"];
    const rows = filtered.map((t) =>
      [t.date, t.ticker, t.strategy, t.direction, t.entry, t.exit, t.pnl, (t.pnlPct * 100).toFixed(2), t.holdTime, t.exitReason, t.slippageBps ?? ""].join(",")
    );
    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `trades-${dateFrom || "start"}-${dateTo || "end"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      <h1 className="text-2xl font-semibold text-zinc-100">Trade log</h1>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div>
          <label className="block text-xs text-zinc-500 mb-1">From</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-500 mb-1">To</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-500 mb-1">Strategy</label>
          <input
            type="text"
            placeholder="Strategy"
            value={strategyFilter}
            onChange={(e) => setStrategyFilter(e.target.value)}
            className="bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white placeholder-zinc-500"
          />
        </div>
        <div>
          <label className="block text-xs text-zinc-500 mb-1">Ticker</label>
          <input
            type="text"
            placeholder="Ticker"
            value={tickerFilter}
            onChange={(e) => setTickerFilter(e.target.value)}
            className="bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white placeholder-zinc-500 font-mono"
          />
        </div>
        <button
          onClick={exportCsv}
          className="mt-6 px-4 py-2 rounded border border-zinc-600 text-zinc-300 hover:bg-zinc-800"
        >
          Export CSV
        </button>
      </div>

      {/* Table */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-zinc-500 border-b border-zinc-800">
                <th className="px-4 py-2">Date</th>
                <th className="px-4 py-2">Ticker</th>
                <th className="px-4 py-2">Strategy</th>
                <th className="px-4 py-2">Direction</th>
                <th className="px-4 py-2">Entry</th>
                <th className="px-4 py-2">Exit</th>
                <th className="px-4 py-2">P&L</th>
                <th className="px-4 py-2">P&L %</th>
                <th className="px-4 py-2">Hold</th>
                <th className="px-4 py-2">Exit reason</th>
                <th className="px-4 py-2">Slippage (bps)</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={11} className="px-4 py-8 text-center text-zinc-500">
                    No trades. Connect backend and run strategies to see history.
                  </td>
                </tr>
              ) : (
                filtered.map((t, i) => (
                  <tr key={i} className="border-b border-zinc-800/50">
                    <td className="px-4 py-2">{t.date}</td>
                    <td className="px-4 py-2 font-mono">{t.ticker}</td>
                    <td className="px-4 py-2">{t.strategy}</td>
                    <td className="px-4 py-2">{t.direction}</td>
                    <td className="px-4 py-2">${t.entry.toFixed(2)}</td>
                    <td className="px-4 py-2">${t.exit.toFixed(2)}</td>
                    <td className={t.pnl >= 0 ? "text-emerald-400" : "text-red-400"}>${t.pnl.toFixed(2)}</td>
                    <td className={t.pnlPct >= 0 ? "text-emerald-400" : "text-red-400"}>
                      {(t.pnlPct * 100).toFixed(2)}%
                    </td>
                    <td className="px-4 py-2">{t.holdTime}</td>
                    <td className="px-4 py-2">{t.exitReason}</td>
                    <td className="px-4 py-2">{t.slippageBps ?? "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
