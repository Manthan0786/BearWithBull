import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from "recharts";
import { useAppStore } from "../store/useAppStore";

const SECTOR_COLORS = ["#22c55e", "#3b82f6", "#a855f7", "#f59e0b", "#ef4444", "#06b6d4", "#ec4899"];

export function RiskMonitor() {
  const riskRules = useAppStore((s) => s.riskRules);
  const dailyLossPct = useAppStore((s) => s.dailyLossPct);
  const dailyLossLimitPct = useAppStore((s) => s.dailyLossLimitPct);
  const alerts = useAppStore((s) => s.alerts);

  const ruleStatusColor = (status: string) =>
    status === "PASS" ? "bg-emerald-500" : status === "WARN" ? "bg-amber-500" : "bg-red-500";

  const dailyPct = Math.min(100, (Math.abs(dailyLossPct) / dailyLossLimitPct) * 100);

  const mockSectors = [
    { name: "Technology", value: 35 },
    { name: "Financials", value: 20 },
    { name: "Healthcare", value: 18 },
    { name: "Consumer", value: 15 },
    { name: "Other", value: 12 },
  ];

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      <h1 className="text-2xl font-semibold text-zinc-100">Risk monitor</h1>

      {/* Risk rules status */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <h2 className="text-sm font-medium text-zinc-400 mb-4">Risk rules</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {riskRules.length === 0 ? (
            <p className="text-zinc-500 col-span-full">No rule data yet. Connect WebSocket for live status.</p>
          ) : (
            riskRules.map((r) => (
              <div
                key={r.ruleName}
                className="flex items-center gap-3 rounded border border-zinc-800 p-3"
              >
                <span className={`w-3 h-3 rounded-full shrink-0 ${ruleStatusColor(r.status)}`} />
                <div>
                  <p className="font-mono text-sm text-zinc-200">{r.ruleName}</p>
                  <p className="text-xs text-zinc-500">{r.scope}</p>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Daily loss gauge */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <h2 className="text-sm font-medium text-zinc-400 mb-2">Daily loss limit</h2>
        <div className="flex items-center gap-4">
          <div className="flex-1 h-6 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-red-500/80 transition-all duration-300"
              style={{ width: `${dailyPct}%` }}
            />
          </div>
          <span className="text-sm font-mono text-zinc-400">
            {dailyLossPct.toFixed(2)}% / {dailyLossLimitPct}%
          </span>
        </div>
      </div>

      {/* Sector exposure */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <h2 className="text-sm font-medium text-zinc-400 mb-4">Sector exposure</h2>
        <div className="h-64 max-w-md">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={mockSectors}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={90}
                paddingAngle={2}
                dataKey="value"
                nameKey="name"
                label={({ name, value }) => `${name} ${value}%`}
              >
                {mockSectors.map((_, i) => (
                  <Cell key={i} fill={SECTOR_COLORS[i % SECTOR_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ backgroundColor: "#18181b", border: "1px solid #27272a" }} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Alert feed */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 overflow-hidden">
        <h2 className="text-sm font-medium text-zinc-400 px-4 py-3 border-b border-zinc-800">
          Alert feed
        </h2>
        <ul className="divide-y divide-zinc-800 max-h-64 overflow-y-auto">
          {alerts.length === 0 ? (
            <li className="px-4 py-6 text-center text-zinc-500">No alerts</li>
          ) : (
            alerts.map((a) => (
              <li key={a.id} className="px-4 py-2 flex gap-3 text-sm">
                <span className="text-zinc-500 shrink-0">{a.time}</span>
                <span
                  className={
                    a.level === "CRITICAL" ? "text-red-400" : a.level === "HIGH" ? "text-amber-400" : "text-zinc-300"
                  }
                >
                  [{a.level}]
                </span>
                <span className="text-zinc-300">{a.message}</span>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
