import { create } from "zustand";
import type {
  PortfolioSummary,
  Position,
  ClosedTrade,
  StrategyState,
  RiskRuleStatus,
  TradeLogEntry,
  TradingStatus,
} from "../types";

interface AppState {
  status: TradingStatus;
  portfolio: PortfolioSummary | null;
  positions: Position[];
  closedTradesToday: ClosedTrade[];
  tradeLog: TradeLogEntry[];
  strategies: StrategyState[];
  riskRules: RiskRuleStatus[];
  dailyLossPct: number;
  dailyLossLimitPct: number;
  alerts: { id: string; time: string; level: string; message: string }[];
  setStatus: (s: TradingStatus) => void;
  setPortfolio: (p: PortfolioSummary | null) => void;
  setPositions: (p: Position[]) => void;
  setClosedTradesToday: (t: ClosedTrade[]) => void;
  setTradeLog: (t: TradeLogEntry[]) => void;
  setStrategies: (s: StrategyState[]) => void;
  setRiskRules: (r: RiskRuleStatus[]) => void;
  setDailyLoss: (pct: number, limit: number) => void;
  setAlerts: (a: { id: string; time: string; level: string; message: string }[]) => void;
  addAlert: (a: { id: string; time: string; level: string; message: string }) => void;
}

export const useAppStore = create<AppState>((set) => ({
  status: "PAPER",
  portfolio: null,
  positions: [],
  closedTradesToday: [],
  tradeLog: [],
  strategies: [],
  riskRules: [],
  dailyLossPct: 0,
  dailyLossLimitPct: 3,
  alerts: [],
  setStatus: (status) => set({ status }),
  setPortfolio: (portfolio) => set({ portfolio }),
  setPositions: (positions) => set({ positions }),
  setClosedTradesToday: (closedTradesToday) => set({ closedTradesToday }),
  setTradeLog: (tradeLog) => set({ tradeLog }),
  setStrategies: (strategies) => set({ strategies }),
  setRiskRules: (riskRules) => set({ riskRules }),
  setDailyLoss: (dailyLossPct, dailyLossLimitPct) => set({ dailyLossPct, dailyLossLimitPct }),
  setAlerts: (alerts) => set({ alerts }),
  addAlert: (alert) =>
    set((s) => ({ alerts: [alert, ...s.alerts].slice(0, 50) })),
}));
