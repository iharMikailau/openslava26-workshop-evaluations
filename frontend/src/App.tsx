import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Outlet, Route, Routes, useNavigate } from "react-router-dom";

import { useCatalog } from "./hooks/useCatalog";
import { Compare } from "./views/Compare";
import { Datasets } from "./views/Datasets";
import { DecisionLab } from "./views/DecisionLab";
import { Ensemble } from "./views/Ensemble";
import { JudgeReliability } from "./views/JudgeReliability";
import { Matrix } from "./views/Matrix";
import { Models } from "./views/Models";
import { Playground } from "./views/Playground";

const PAGES = [
  { path: "/playground", label: "Playground" },
  { path: "/matrix", label: "Matrix" },
  { path: "/compare", label: "Compare" },
  { path: "/ensemble", label: "Ensemble" },
  { path: "/judge-reliability", label: "Judge reliability" },
  { path: "/decision-judges", label: "Decision judges" },
  { path: "/datasets", label: "Datasets" },
  { path: "/models", label: "Models" },
];

function usePreferredTheme() {
  const [theme, setTheme] = useState<"light" | "dark">(() =>
    window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light",
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  return { theme, setTheme };
}

export function App() {
  const { catalog, error, refresh } = useCatalog();
  const navigate = useNavigate();
  const { theme, setTheme } = usePreferredTheme();

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__brand">
          <span className="topbar__title">Evaluation Lab</span>
          <span className="topbar__subtitle">prompts · models · evaluation mechanisms</span>
        </div>
        <div className="topbar__spacer" />
        <nav className="tabs">
          {PAGES.map(({ path, label }) => (
            <NavLink key={path} to={path} end className={({ isActive }) => `tab ${isActive ? "tab--active" : ""}`}>
              {label}
            </NavLink>
          ))}
        </nav>
        <button
          className="icon-button"
          title="Toggle light and dark"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          {theme === "dark" ? "☾" : "☀"}
        </button>
      </header>

      <Routes>
        <Route element={<main className="content"><Outlet /></main>}>
          <Route index element={<Navigate to="/playground" replace />} />
          <Route path="*" element={<div><h1>Page not found</h1><p>The requested page could not be found.</p><Link to="/playground" onClick={() => { if (error) refresh(); }}>Go to Playground</Link></div>} />
          {[
            ["/playground", catalog && <Playground catalog={catalog} />],
            ["/matrix", catalog && <Matrix catalog={catalog} />],
            ["/compare", catalog && <Compare catalog={catalog} />],
            ["/ensemble", catalog && <Ensemble catalog={catalog} />],
            ["/judge-reliability", catalog && <JudgeReliability catalog={catalog} />],
            ["/decision-judges", catalog && <DecisionLab catalog={catalog} openModels={() => navigate("/models")} />],
            ["/datasets", catalog && <Datasets catalog={catalog} onChange={refresh} />],
            ["/models", catalog && <Models onChange={refresh} />],
          ].map(([path, view]) => (
            <Route key={path as string} path={path as string} element={<>{error && <div className="banner">{error}</div>}{!catalog && !error && <p className="muted">Loading catalogue…</p>}{catalog && view}</>} />
          ))}
        </Route>
      </Routes>
    </div>
  );
}
