import { useState } from "react";
import { useAppStore } from "../store/useAppStore";

const API_BASE = "";

export function StrategyPanel() {
  const strategies = useAppStore((s) => s.strategies);
  const setStrategies = useAppStore((s) => s.setStrategies);
  const [emergencyConfirm, setEmergencyConfirm] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [emergencyLoading, setEmergencyLoading] = useState(false);
  const [emergencyError, setEmergencyError] = useState<string | null>(null);

  const defaultStrategies = [
    { id: "momentum_breakout", name: "Momentum Breakout", enabled: true, totalTrades: 0, winRate: 0, avgWin: 0, avgLoss: 0, profitFactor: 0, sharpe30d: 0, avgHoldTime: "-" },
    { id: "stat_mean_reversion", name: "Stat Mean Reversion", enabled: true, totalTrades: 0, winRate: 0, avgWin: 0, avgLoss: 0, profitFactor: 0, sharpe30d: 0, avgHoldTime: "-" },
    { id: "sentiment_catalyst", name: "Sentiment Catalyst", enabled: true, totalTrades: 0, winRate: 0, avgWin: 0, avgLoss: 0, profitFactor: 0, sharpe30d: 0, avgHoldTime: "-" },
  ];
  const list = strategies.length > 0 ? strategies : defaultStrategies;

  const handleEmergencyStop = async () => {
    if (!emergencyConfirm) {
      setEmergencyConfirm(true);
      setEmergencyError(null);
      return;
    }
    if (confirmText !== "CONFIRM") return;
    setEmergencyLoading(true);
    setEmergencyError(null);
    try {
      const res = await fetch(`${API_BASE}/api/emergency-stop`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: "CONFIRM" }),
      });
      const data = await res.json();
      if (!res.ok) {
        setEmergencyError(data.detail?.toString() || res.statusText || "Request failed");
        return;
      }
      if (data.ok === false && data.errors?.length) {
        setEmergencyError(data.errors[0] || "Request rejected");
        return;
      }
      const msg = data.errors?.length
        ? `Emergency stop: ${data.cancelled_orders} orders cancelled, ${data.flatten_orders_placed} flatten orders placed. Warnings: ${data.errors.join("; ")}`
        : `Emergency stop executed. ${data.cancelled_orders} orders cancelled, ${data.flatten_orders_placed} positions flatten orders placed.`;
      useAppStore.getState().setStatus("HALTED");
      useAppStore.getState().addAlert({
        id: String(Date.now()),
        time: new Date().toISOString().slice(11, 19),
        level: "CRITICAL",
        message: msg,
      });
      setEmergencyConfirm(false);
      setConfirmText("");
    } catch (e) {
      setEmergencyError(e instanceof Error ? e.message : "Network error");
    } finally {
      setEmergencyLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      <h1 className="text-2xl font-semibold text-zinc-100">Strategy control</h1>

      {/* Emergency stop */}
      <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-4">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h2 className="text-sm font-medium text-red-400">Emergency stop</h2>
            <p className="text-xs text-zinc-500 mt-1">
              Cancels all open orders and closes all positions with market orders via IBKR.
            </p>
            {emergencyError && (
              <p className="text-xs text-red-400 mt-2">{emergencyError}</p>
            )}
          </div>
          {!emergencyConfirm ? (
            <button
              onClick={handleEmergencyStop}
              disabled={emergencyLoading}
              className="px-6 py-2 rounded font-semibold bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white"
            >
              {emergencyLoading ? "Executing…" : "Emergency stop"}
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Type CONFIRM"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                className="bg-zinc-800 border border-zinc-700 rounded px-3 py-2 text-white placeholder-zinc-500 font-mono"
                disabled={emergencyLoading}
              />
              <button
                onClick={handleEmergencyStop}
                disabled={confirmText !== "CONFIRM" || emergencyLoading}
                className="px-4 py-2 rounded font-semibold bg-red-600 hover:bg-red-500 disabled:opacity-50 disabled:cursor-not-allowed text-white"
              >
                {emergencyLoading ? "Executing…" : "Execute"}
              </button>
              <button
                onClick={() => { setEmergencyConfirm(false); setConfirmText(""); setEmergencyError(null); }}
                disabled={emergencyLoading}
                className="px-4 py-2 rounded border border-zinc-600 text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Strategy toggles and stats */}
      <div className="space-y-4">
        {list.map((s) => (
          <div
            key={s.id}
            className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4"
          >
            <div className="flex items-center justify-between flex-wrap gap-4">
              <div className="flex items-center gap-4">
                <h2 className="text-lg font-medium text-zinc-200">{s.name}</h2>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={s.enabled}
                    onChange={async () => {
                      try {
                        const res = await fetch(`${API_BASE}/api/strategies/${s.id}`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({ enabled: !s.enabled }),
                        });
                        if (!res.ok) return;
                        const updated = await res.json();
                        setStrategies(
                          list.map((st) =>
                            st.id === s.id
                              ? {
                                  ...st,
                                  enabled: updated.enabled,
                                  totalTrades: updated.totalTrades,
                                  winRate: updated.winRate,
                                  avgWin: updated.avgWin,
                                  avgLoss: updated.avgLoss,
                                  profitFactor: updated.profitFactor,
                                  sharpe30d: updated.sharpe30d,
                                  avgHoldTime: updated.avgHoldTime,
                                }
                              : st,
                          ),
                        );
                      } catch {
                        // ignore network errors for toggle
                      }
                    }}
                    className="rounded border-zinc-600 bg-zinc-800 text-emerald-500 focus:ring-emerald-500"
                  />
                  <span className="text-sm text-zinc-400">Enabled</span>
                </label>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mt-4 text-sm">
              <div><span className="text-zinc-500">Trades</span><p className="font-mono text-zinc-200">{s.totalTrades}</p></div>
              <div><span className="text-zinc-500">Win rate</span><p className="font-mono text-zinc-200">{(s.winRate * 100).toFixed(1)}%</p></div>
              <div><span className="text-zinc-500">Avg win</span><p className="font-mono text-emerald-400">${s.avgWin.toFixed(2)}</p></div>
              <div><span className="text-zinc-500">Avg loss</span><p className="font-mono text-red-400">${s.avgLoss.toFixed(2)}</p></div>
              <div><span className="text-zinc-500">Profit factor</span><p className="font-mono text-zinc-200">{s.profitFactor.toFixed(2)}</p></div>
              <div><span className="text-zinc-500">Sharpe (30d)</span><p className="font-mono text-zinc-200">{s.sharpe30d.toFixed(2)}</p></div>
            </div>
          </div>
        ))}
      </div>

      {/* Config sliders placeholder */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <h2 className="text-sm font-medium text-zinc-400 mb-4">Risk config</h2>
        <p className="text-zinc-500 text-sm">Max position %, daily loss limit %, max positions, risk per trade — configurable via backend when API is wired.</p>
      </div>
    </div>
  );
}
