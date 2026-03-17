import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "./components/Layout";
import { useApiSync } from "./hooks/useApiSync";
import { Overview } from "./pages/Overview";
import { RiskMonitor } from "./pages/RiskMonitor";
import { StrategyPanel } from "./pages/StrategyPanel";
import { TradeLog } from "./pages/TradeLog";
import { Backtester } from "./pages/Backtester";

export default function App() {
  useApiSync(10_000);
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Overview />} />
          <Route path="risk" element={<RiskMonitor />} />
          <Route path="strategies" element={<StrategyPanel />} />
          <Route path="trades" element={<TradeLog />} />
          <Route path="backtest" element={<Backtester />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
