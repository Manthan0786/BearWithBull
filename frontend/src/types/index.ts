export interface PortfolioSummary {
  nav: number;
  cash: number;
  dailyPnl: number;
  dailyPnlPct: number;
  allTimePnl: number;
  winRate30d: number;
}

export interface Position {
  ticker: string;
  strategy: string;
  direction: "LONG" | "SHORT";
  entryPrice: number;
  currentPrice: number;
  unrealizedPnl: number;
  stopPrice: number;
  distanceToStop: number;
  holdTime: string;
  atr: number;
}

export interface ClosedTrade {
  ticker: string;
  strategy: string;
  entry: number;
  exit: number;
  pnl: number;
  pnlPct: number;
  holdTime: string;
  exitReason: string;
}

export interface StrategyState {
  id: string;
  name: string;
  enabled: boolean;
  totalTrades: number;
  winRate: number;
  avgWin: number;
  avgLoss: number;
  profitFactor: number;
  sharpe30d: number;
  avgHoldTime: string;
}

export interface RiskRuleStatus {
  ruleName: string;
  scope: string;
  status: "PASS" | "WARN" | "FAIL";
  details?: Record<string, unknown>;
}

export interface TradeLogEntry {
  date: string;
  ticker: string;
  strategy: string;
  direction: string;
  entry: number;
  exit: number;
  pnl: number;
  pnlPct: number;
  holdTime: string;
  exitReason: string;
  slippageBps: number | null;
}

export type TradingStatus = "ACTIVE" | "HALTED" | "PAPER";
