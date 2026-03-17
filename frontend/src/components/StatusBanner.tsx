import { Link } from "react-router-dom";
import { useAppStore } from "../store/useAppStore";

export function StatusBanner() {
  const status = useAppStore((s) => s.status);
  const statusConfig = {
    ACTIVE: { bg: "bg-emerald-900/80", text: "ACTIVE", border: "border-emerald-600" },
    HALTED: { bg: "bg-amber-900/80", text: "HALTED", border: "border-amber-600" },
    PAPER: { bg: "bg-sky-900/50", text: "PAPER MODE", border: "border-sky-500" },
  };
  const cfg = statusConfig[status] ?? statusConfig.PAPER;
  return (
    <div
      className={`flex items-center justify-between px-4 py-2 border-b ${cfg.border} ${cfg.bg} border-b-2`}
    >
      <div className="flex items-center gap-4">
        <span className={`font-mono font-semibold uppercase tracking-wider ${cfg.text === "ACTIVE" ? "text-emerald-400" : cfg.text === "HALTED" ? "text-amber-400" : "text-sky-400"}`}>
          {cfg.text}
        </span>
        <nav className="flex gap-2 text-sm items-center flex-wrap">
          <Link to="/" className="text-zinc-400 hover:text-white px-2 py-1 rounded">
            Overview
          </Link>
          <Link to="/risk" className="text-zinc-400 hover:text-white px-2 py-1 rounded">
            Risk
          </Link>
          <Link to="/strategies" className="text-zinc-400 hover:text-white px-2 py-1 rounded">
            Strategies
          </Link>
          <Link to="/trades" className="text-zinc-400 hover:text-white px-2 py-1 rounded">
            Trade Log
          </Link>
          <Link to="/backtest" className="text-zinc-400 hover:text-white px-2 py-1 rounded">
            Backtest
          </Link>
          <Link
            to="/strategies"
            className="ml-2 px-3 py-1 rounded font-medium bg-red-600 hover:bg-red-500 text-white"
          >
            Emergency stop
          </Link>
        </nav>
      </div>
    </div>
  );
}
