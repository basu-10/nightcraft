import { Navigate, useLocation } from "react-router-dom";

export default function AdminRoute({ user, children }) {
  const location = useLocation();

  if (!user) {
    const nextTarget = `${location.pathname}${location.search}` || "/";
    return <Navigate to={`/login?next=${encodeURIComponent(nextTarget)}`} replace />;
  }
  if (!user.is_admin) return <Navigate to="/" replace />;
  return children;
}
