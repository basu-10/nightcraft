import { Navigate, useLocation } from "react-router-dom";

// user is resolved by App before rendering routes — no redundant fetch needed
export default function ProtectedRoute({ user, children }) {
  const location = useLocation();

  if (!user) {
    const nextTarget = `${location.pathname}${location.search}` || "/";
    return <Navigate to={`/login?next=${encodeURIComponent(nextTarget)}`} replace />;
  }
  return children;
}
