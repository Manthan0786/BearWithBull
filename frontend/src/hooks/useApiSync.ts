import { useEffect, useRef } from "react";
import { useAppStore } from "../store/useAppStore";

const API_BASE = "";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

export function useApiSync(intervalMs = 10_000) {
  const setStatus = useAppStore((s) => s.setStatus);
  const setPortfolio = useAppStore((s) => s.setPortfolio);
  const setPositions = useAppStore((s) => s.setPositions);
  const setClosedTradesToday = useAppStore((s) => s.setClosedTradesToday);
  const setTradeLog = useAppStore((s) => s.setTradeLog);
  const setStrategies = useAppStore((s) => s.setStrategies);
  const setRiskRules = useAppStore((s) => s.setRiskRules);
  const setDailyLoss = useAppStore((s) => s.setDailyLoss);
  const setAlerts = useAppStore((s) => s.setAlerts);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;

    const sync = async () => {
      if (!mounted.current) return;
      try {
        const [status, portfolio, positions, tradesToday, trades, strategies, risk, alerts] = await Promise.all([
          fetchJson<{ status: string }>("/api/status"),
          fetchJson<Parameters<typeof setPortfolio>[0]>("/api/portfolio"),
          fetchJson<Parameters<typeof setPositions>[0]>("/api/positions"),
          fetchJson<Parameters<typeof setClosedTradesToday>[0]>("/api/trades/today"),
          fetchJson<Parameters<typeof setTradeLog>[0]>("/api/trades"),
          fetchJson<Parameters<typeof setStrategies>[0]>("/api/strategies"),
          fetchJson<{ rules: Parameters<typeof setRiskRules>[0]; dailyLossPct: number; dailyLossLimitPct: number }>("/api/risk"),
          fetchJson<{ id: string; time: string; level: string; message: string }[]>("/api/alerts"),
        ]);
        if (!mounted.current) return;
        setStatus(status.status as "ACTIVE" | "HALTED" | "PAPER");
        setPortfolio(portfolio);
        setPositions(positions);
        setClosedTradesToday(tradesToday);
        setTradeLog(trades);
        setStrategies(strategies);
        setRiskRules(risk.rules);
        setDailyLoss(risk.dailyLossPct, risk.dailyLossLimitPct);
        setAlerts(alerts.map((a) => ({ id: a.id, time: a.time.slice(11, 19), level: a.level, message: a.message })));
      } catch {
        // ignore network errors; keep previous state
      }
    };

    sync();
    const id = setInterval(sync, intervalMs);
    return () => {
      mounted.current = false;
      clearInterval(id);
    };
  }, [
    intervalMs,
    setStatus,
    setPortfolio,
    setPositions,
    setClosedTradesToday,
    setTradeLog,
    setStrategies,
    setRiskRules,
    setDailyLoss,
    setAlerts,
  ]);
}
