import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

/**
 * Wraps any route that requires authentication.
 * Unauthenticated users are redirected to /login,
 * preserving the intended destination in location.state.
 */
export function ProtectedRoute({ children, requiredRole = null }) {
  const { isLoggedIn, user } = useAuthStore();
  const location = useLocation();

  if (!isLoggedIn) {
    return (
      <Navigate
        to="/login"
        state={{ from: location.pathname }}
        replace
      />
    );
  }

  if (requiredRole && user?.role !== requiredRole) {
    return <Navigate to="/" replace />;
  }

  return children;
}

/**
 * Wraps public-only routes (login, signup, home).
 * Already-authenticated users skip straight to the dashboard.
 */
export function PublicRoute({ children }) {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn);
  if (isLoggedIn) return <Navigate to="/dashboard" replace />;
  return children;
}
