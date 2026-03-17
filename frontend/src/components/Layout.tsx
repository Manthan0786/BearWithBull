import { Outlet } from "react-router-dom";
import { StatusBanner } from "./StatusBanner";

export function Layout() {
  return (
    <div className="min-h-screen flex flex-col bg-[#0d0d0d]">
      <StatusBanner />
      <main className="flex-1 p-6 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
