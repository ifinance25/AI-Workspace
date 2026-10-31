import { type JSX } from "react";
import LoadingCenter from "@/components/uikit/LoadingCenter";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "@/auth/AuthContext";
import { ModelInfoProvider } from "@/lib/ModelInfoContext";
import AdminPage from "@/routes/AdminPage";
import ChatPage from "@/routes/ChatPage";
import LoginPage from "@/routes/LoginPage";
import OfficePage from "@/routes/OfficePage";
import RedminePage from "@/routes/RedminePage";
import RunsPage from "@/routes/RunsPage";
import SettingsPage from "@/routes/SettingsPage";
import { ROUTER_BASENAME } from "@/api/base";

function Protected({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex h-screen min-h-0 flex-col bg-[var(--bg-canvas)]">
        <LoadingCenter label="Загрузка…" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function AdminOnly({ children }: { children: JSX.Element }) {
  const { user } = useAuth();
  if (!user?.is_admin) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <AuthProvider>
      <ModelInfoProvider>
        <BrowserRouter basename={ROUTER_BASENAME}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/"
              element={
                <Protected>
                  <ChatPage />
                </Protected>
              }
            />
            <Route
              path="/settings"
              element={
                <Protected>
                  <SettingsPage />
                </Protected>
              }
            />
            <Route
              path="/office"
              element={
                <Protected>
                  <OfficePage />
                </Protected>
              }
            />
            <Route
              path="/office/:id"
              element={
                <Protected>
                  <OfficePage />
                </Protected>
              }
            />
            <Route
              path="/office/:id/redmine"
              element={
                <Protected>
                  <RedminePage />
                </Protected>
              }
            />
            <Route
              path="/office/:id/runs"
              element={
                <Protected>
                  <RunsPage />
                </Protected>
              }
            />
            <Route
              path="/admin"
              element={
                <Protected>
                  <AdminOnly>
                    <AdminPage />
                  </AdminOnly>
                </Protected>
              }
            />
          </Routes>
        </BrowserRouter>
      </ModelInfoProvider>
    </AuthProvider>
  );
}
