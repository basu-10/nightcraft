import { Suspense, lazy, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import ProtectedRoute from "./components/ProtectedRoute";
import AdminRoute from "./components/AdminRoute";
import AuthenticatedShell from "./components/AuthenticatedShell";
import LoginPage from "./pages/LoginPage";
import { api } from "./api";

const MainPage = lazy(() => import("./pages/MainPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));
const NotesPage = lazy(() => import("./pages/NotesPage"));
const NotificationsPage = lazy(() => import("./pages/NotificationsPage"));
const GlobalSettingsPage = lazy(() => import("./pages/GlobalSettingsPage"));
const AccountPage = lazy(() => import("./pages/AccountPage"));

export default function App() {
  const [user, setUser] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);

  useEffect(() => {
    api.me()
      .then((res) => {
        setUser(res?.authenticated ? res.user : null);
      })
      .catch(() => setUser(null))
      .finally(() => setAuthLoading(false));
  }, []);

  const handleLogout = () => setUser(null);

  const withShell = (node) => (
    <AuthenticatedShell user={user} onLogout={handleLogout}>
      <Suspense fallback={<div className="page-shell">Loading…</div>}>{node}</Suspense>
    </AuthenticatedShell>
  );

  if (authLoading) {
    return <div className="page-shell">Loading…</div>;
  }

  return (
    <Routes>
      <Route path="/login" element={
        user ? <Navigate to="/" replace /> : <LoginPage />
      } />
      <Route path="/" element={
        user
          ? withShell(<MainPage user={user} onLogout={handleLogout} />)
          : <LoginPage />
      } />
      <Route path="/dashboard" element={
        <ProtectedRoute user={user}>
          {withShell(<DashboardPage />)}
        </ProtectedRoute>
      } />
      <Route path="/notes" element={
        <ProtectedRoute user={user}>
          {withShell(<NotesPage />)}
        </ProtectedRoute>
      } />
      <Route path="/notifications" element={
        <ProtectedRoute user={user}>
          {withShell(<NotificationsPage />)}
        </ProtectedRoute>
      } />
      <Route path="/global-settings" element={
        <ProtectedRoute user={user}>
          {withShell(<GlobalSettingsPage />)}
        </ProtectedRoute>
      } />
      <Route path="/account" element={
        <ProtectedRoute user={user}>
          {withShell(<AccountPage user={user} />)}
        </ProtectedRoute>
      } />
      <Route path="/admin" element={
        <AdminRoute user={user}>
          {withShell(<AdminPage />)}
        </AdminRoute>
      } />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
