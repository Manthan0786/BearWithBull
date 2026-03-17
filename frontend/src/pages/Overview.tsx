import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { useAppStore } from "../store/useAppStore";

const mockEquity = [
  { date: "03/10", value: 100000, spy: 0 },
  { date: "03/11", value: 100200, spy: 0.1 },
  { date: "03/12", value: 100150, spy: -0.05 },
  { date: "03/13", value: 100500, spy: 0.2 },
  { date: "03/14", value: 101000, spy: 0.4 },
  { date: "03/15", value: 100800, spy: 0.3 },
];

export function Overview() {
  const portfolio = useAppStore((s) => s.portfolio);
  const positions = useAppStore((s) => s.positions);
  const closedTradesToday = useAppStore((s) => s.closedTradesToday);

  const nav = portfolio?.nav ?? 0;
  const cash = portfolio?.cash ?? 0;
  const dailyPnl = portfolio?.dailyPnl ?? 0;
  const dailyPnlPct = portfolio?.dailyPnlPct ?? 0;
  const allTimePnl = portfolio?.allTimePnl ?? 0;
  const winRate = portfolio?.winRate30d ?? 0;

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      <h1 className="text-2xl font-semibold text-zinc-100">Overview</h1>

      {/* Top bar metrics */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
        <MetricCard label="NAV (USD)" value={`$${nav.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} />
        <MetricCard label="Cash" value={`$${cash.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} />
        <MetricCard
          label="Daily P&L"
          value={`$${dailyPnl.toFixed(2)}`}
          sub={`${(dailyPnlPct * 100).toFixed(2)}%`}
          positive={dailyPnl >= 0}
        />
        <MetricCard
          label="All-time P&L"
          value={`$${allTimePnl.toFixed(2)}`}
          positive={allTimePnl >= 0}
        />
        <MetricCard label="Win rate (30d)" value={`${(winRate * 100).toFixed(1)}%`} />
      </div>

      {/* Equity curve */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <h2 className="text-sm font-medium text-zinc-400 mb-4">Equity curve vs SPY</h2>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={mockEquity} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
              <XAxis dataKey="date" stroke="#71717a" fontSize={12} />
              <YAxis stroke="#71717a" fontSize={12} tickFormatter={(v) => `$${v}`} />
              <Tooltip
                contentStyle={{ backgroundColor: "#18181b", border: "1px solid #27272a" }}
                formatter={(value: number) => [value, ""]}
              />
              <Legend />
              <Line type="monotone" dataKey="value" stroke="#22c55e" name="Portfolio" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="spy" stroke="#3b82f6" name="SPY %" strokeWidth={1} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Active positions */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 overflow-hidden">
        <h2 className="text-sm font-medium text-zinc-400 px-4 py-3 border-b border-zinc-800">
          Active positions
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-zinc-500 border-b border-zinc-800">
                <th className="px-4 py-2">Ticker</th>
                <th className="px-4 py-2">Strategy</th>
                <th className="px-4 py-2">Direction</th>
                <th className="px-4 py-2">Entry</th>
                <th className="px-4 py-2">Current</th>
                <th className="px-4 py-2">Unrealized P&L</th>
                <th className="px-4 py-2">Stop</th>
                <th className="px-4 py-2">Hold</th>
              </tr>
            </thead>
            <tbody>
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-zinc-500">
                    No open positions
                  </td>
                </tr>
              ) : (
                positions.map((p) => (
                  <tr key={`${p.ticker}-${p.strategy}`} className="border-b border-zinc-800/50">
                    <td className="px-4 py-2 font-mono">{p.ticker}</td>
                    <td className="px-4 py-2">{p.strategy}</td>
                    <td className="px-4 py-2">{p.direction}</td>
                    <td className="px-4 py-2">${p.entryPrice.toFixed(2)}</td>
                    <td className="px-4 py-2">${p.currentPrice.toFixed(2)}</td>
                    <td className={`px-4 py-2 ${p.unrealizedPnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      ${p.unrealizedPnl.toFixed(2)}
                    </td>
                    <td className="px-4 py-2">${p.stopPrice.toFixed(2)}</td>
                    <td className="px-4 py-2">{p.holdTime}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Today's closed trades */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 overflow-hidden">
        <h2 className="text-sm font-medium text-zinc-400 px-4 py-3 border-b border-zinc-800">
          Today&apos;s closed trades
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-zinc-500 border-b border-zinc-800">
                <th className="px-4 py-2">Ticker</th>
                <th className="px-4 py-2">Strategy</th>
                <th className="px-4 py-2">Entry</th>
                <th className="px-4 py-2">Exit</th>
                <th className="px-4 py-2">P&L</th>
                <th className="px-4 py-2">P&L %</th>
                <th className="px-4 py-2">Hold</th>
                <th className="px-4 py-2">Exit reason</th>
              </tr>
            </thead>
            <tbody>
              {closedTradesToday.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-zinc-500">
                    No closed trades today
                  </td>
                </tr>
              ) : (
                closedTradesToday.map((t, i) => (
                  <tr key={i} className="border-b border-zinc-800/50">
                    <td className="px-4 py-2 font-mono">{t.ticker}</td>
                    <td className="px-4 py-2">{t.strategy}</td>
                    <td className="px-4 py-2">${t.entry.toFixed(2)}</td>
                    <td className="px-4 py-2">${t.exit.toFixed(2)}</td>
                    <td className={t.pnl >= 0 ? "text-emerald-400" : "text-red-400"}>${t.pnl.toFixed(2)}</td>
                    <td className={t.pnlPct >= 0 ? "text-emerald-400" : "text-red-400"}>
                      {(t.pnlPct * 100).toFixed(2)}%
                    </td>
                    <td className="px-4 py-2">{t.holdTime}</td>
                    <td className="px-4 py-2">{t.exitReason}</td>
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

function MetricCard({
  label,
  value,
  sub,
  positive,
}: {
  label: string;
  value: string;
  sub?: string;
  positive?: boolean;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
      <p className="text-xs text-zinc-500 uppercase tracking-wider">{label}</p>
      <p className={`text-lg font-mono font-semibold ${positive === true ? "text-emerald-400" : positive === false ? "text-red-400" : "text-zinc-100"}`}>
        {value}
      </p>
      {sub != null && <p className="text-sm text-zinc-400">{sub}</p>}
    </div>
  );
}
