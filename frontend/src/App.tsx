import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Ingest from "./pages/Ingest";
import Review from "./pages/Review";
import Anomalies from "./pages/Anomalies";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem("auth_token");
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="ingest" element={<Ingest />} />
          <Route path="review" element={<Review />} />
          <Route path="anomalies" element={<Anomalies />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
