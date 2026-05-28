import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { logout } from "../api/client";

const navItems = [
  { to: "/dashboard", label: "Dashboard", icon: "▦" },
  { to: "/ingest", label: "Ingest Data", icon: "↑" },
  { to: "/review", label: "Review Queue", icon: "✓" },
  { to: "/anomalies", label: "Anomalies", icon: "⚠" },
];

export default function Layout() {
  const navigate = useNavigate();

  async function handleLogout() {
    try { await logout(); } catch {}
    localStorage.removeItem("auth_token");
    navigate("/login");
  }

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-56 bg-brand-800 text-white flex flex-col shrink-0">
        <div className="px-5 py-5 border-b border-brand-700">
          <div className="text-xs font-semibold text-brand-300 uppercase tracking-widest mb-0.5">Breathe ESG</div>
          <div className="text-lg font-bold">Data Review</div>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-0.5">
          {navItems.map(({ to, label, icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-brand-600 text-white"
                    : "text-brand-100 hover:bg-brand-700 hover:text-white"
                }`
              }
            >
              <span className="text-base">{icon}</span>
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-3 py-4 border-t border-brand-700">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium text-brand-100 hover:bg-brand-700 hover:text-white transition-colors"
          >
            <span>⏏</span> Sign out
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 flex flex-col min-w-0">
        <div className="flex-1 overflow-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
