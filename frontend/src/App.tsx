/**
 * Application shell and routing.
 *
 * The landing page stands on its own — no chrome, no counter furniture. Every
 * console screen shares the plum header and the trust-class legend, because an
 * officer who cannot see the legend cannot read the evidence.
 */
import { HashRouter, NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
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
  const reduce = useReducedMotion();
  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <header className="sticky top-0 z-50 bg-intaglio text-paper">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-6 py-3">
          <NavLink to="/" className="text-[length:var(--text-evidence)] font-semibold tracking-[-0.02em] hover:opacity-80 transition-opacity">
            Sashastra Seema Bal
          </NavLink>
          <span className="ml-auto flex items-center gap-4">
            <Clock />
            <span className="hidden sm:inline-block h-4 w-px bg-white/20" />
            <span className="text-label text-white/60">Officer 4471</span>
          </span>
        </div>

        <nav className="mx-auto flex max-w-7xl gap-1 px-6 pb-0">
          {NAV.map((n) => {
            const active = pathname.startsWith(n.to);
            return (
              <NavLink
                key={n.to}
                to={n.to}
                className={cn(
                  "relative px-4 py-2.5 text-label font-medium rounded-t-[var(--radius-md)] transition-colors",
                  active ? "text-intaglio" : "text-white/60 hover:text-white hover:bg-white/5",
                )}
              >
                {active && (
                  <motion.span
                    layoutId="nav-active"
                    className="absolute inset-0 -z-10 rounded-t-[var(--radius-md)] bg-paper"
                    transition={reduce ? { duration: 0 } : { type: "spring", stiffness: 500, damping: 35 }}
                  />
                )}
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
