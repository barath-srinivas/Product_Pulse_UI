import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import OperatorPage from "./pages/OperatorPage";

// Local dev: on by default. Production (Vercel): set VITE_ENABLE_OPERATOR=false
const operatorFlag = import.meta.env.VITE_ENABLE_OPERATOR;
const operatorEnabled =
  operatorFlag === "true" || (import.meta.env.DEV && operatorFlag !== "false");
export default function App() {
  return (
    <>
      <nav className="nav">
        <h1>Product Review Pulse</h1>
        <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
          Dashboard
        </NavLink>
        {operatorEnabled && (
          <NavLink to="/operator" className={({ isActive }) => (isActive ? "active" : "")}>
            Operator
          </NavLink>
        )}
      </nav>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        {operatorEnabled ? (
          <Route path="/operator" element={<OperatorPage />} />
        ) : (
          <Route path="/operator" element={<Navigate to="/" replace />} />
        )}
      </Routes>
    </>
  );
}
