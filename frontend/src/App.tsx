/**
 * Application shell and routing.
 *
 * The landing page stands on its own — no chrome, no counter furniture. Every
 * console screen shares the plum header and the trust-class legend, because an
 * officer who cannot see the legend cannot read the evidence.
 */
import { HashRouter, NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { Landing } from "./screens/Landing";
import { Capture } from "./screens/Capture";
import { Screening } from "./screens/Screening";
import { Session } from "./screens/Session";
import { OperatingPoint } from "./screens/OperatingPoint";
import { Audit } from "./screens/Audit";
import { Legend } from "./components/Legend";
import { cn } from "./lib/utils";

const NAV = [
  { to: "/capture", label: "Capture" },
  { to: "/screening", label: "Screening" },
  { to: "/session", label: "Session" },
  { to: "/operating-point", label: "Operating point" },
  { to: "/audit", label: "Audit" },
];

function Clock() {
  const now = new Date().toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return <span className="data text-bloom/80">{now}</span>;
}

function ConsoleShell() {
  const { pathname } = useLocation();
  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <header className="bg-intaglio text-paper">
        <div className="flex items-baseline gap-6 px-8 pt-3">
          <NavLink to="/" className="font-semibold tracking-tight hover:underline">
            Sashastra Seema Bal
          </NavLink>
          <span className="text-bloom/80">Raxaul integrated check post</span>
          <span className="ml-auto">
            <Clock />
          </span>
          <span className="text-bloom/80">Officer 4471</span>
        </div>

        <nav className="flex gap-1 px-8 pt-3">
          {NAV.map((n) => {
            const active = pathname.startsWith(n.to);
            return (
              <NavLink
                key={n.to}
                to={n.to}
                className={cn(
                  "border-b-2 px-3 py-2 text-label transition-colors",
                  active
                    ? "border-guilloche text-paper"
                    : "border-transparent text-bloom/70 hover:text-paper",
                )}
              >
                {n.label}
              </NavLink>
            );
          })}
        </nav>
      </header>

      <main className="flex min-h-0 flex-1 flex-col">
        <Outlet />
      </main>

      <Legend />
    </div>
  );
}

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route element={<ConsoleShell />}>
          <Route path="/capture" element={<Capture />} />
          <Route path="/screening" element={<Screening />} />
          <Route path="/session" element={<Session />} />
          <Route path="/operating-point" element={<OperatingPoint />} />
          <Route path="/audit" element={<Audit />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
