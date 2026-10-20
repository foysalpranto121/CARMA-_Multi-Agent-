import './index.css';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

/* Auth */
import { PublicRoute, ProtectedRoute } from './components/AuthGuard';
import { useAuthStore } from './store/authStore';

/* Public pages */
import HomePage   from './pages/HomePage';
import LoginPage  from './pages/LoginPage';
import SignupPage from './pages/SignupPage';

/* App shell (authenticated layout) */
import Sidebar    from './components/Sidebar';
import TopBar     from './components/TopBar';
import Dashboard     from './pages/Dashboard';
import NotFoundPage from './pages/NotFoundPage';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

/* ── Placeholder for pages built in Day 2-3 ── */
const Placeholder = ({ name }) => (
  <div className="page-wrapper">
    <div className="glass-card" style={{ textAlign: 'center', padding: 80 }}>
      <div className="holo-subtitle" style={{ marginBottom: 16 }}>{name}</div>
      <h2 className="holo-title" style={{ fontSize: 28 }}>Coming in Day 2–3</h2>
      <p style={{ color: 'var(--text-muted)', marginTop: 16, fontSize: 13, lineHeight: 1.7 }}>
        This module is implemented in the Day 2–3 sprint blocks.
        <br />See the{' '}
        <a href="#" style={{ color: 'var(--holo-cyan)' }}>implementation plan</a>
        {' '}for details.
      </p>
    </div>
  </div>
);

/* ── Authenticated layout wrapper ── */
function AppLayout({ children }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-content">
        <TopBar systemOnline={true} />
        {children}
      </div>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>

          {/* ── PUBLIC routes (redirect to /dashboard if already logged in) ── */}
          <Route
            path="/"
            element={
              <PublicRoute>
                <HomePage />
              </PublicRoute>
            }
          />
          <Route
            path="/login"
            element={
              <PublicRoute>
                <LoginPage />
              </PublicRoute>
            }
          />
          <Route
            path="/signup"
            element={
              <PublicRoute>
                <SignupPage />
              </PublicRoute>
            }
          />

          {/* ── PROTECTED routes (redirect to /login if not authenticated) ── */}
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <AppLayout>
                  <Dashboard />
                </AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/processes"
            element={
              <ProtectedRoute>
                <AppLayout><Placeholder name="PROCESSES" /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/benchmark"
            element={
              <ProtectedRoute>
                <AppLayout><Placeholder name="WF-ADAPT BENCHMARK" /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/experiments"
            element={
              <ProtectedRoute>
                <AppLayout><Placeholder name="EXPERIMENTS" /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/experiments/new"
            element={
              <ProtectedRoute>
                <AppLayout><Placeholder name="NEW EXPERIMENT" /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/experiments/:id"
            element={
              <ProtectedRoute>
                <AppLayout><Placeholder name="EXPERIMENT DETAIL" /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/metrics"
            element={
              <ProtectedRoute>
                <AppLayout><Placeholder name="METRICS & STATISTICS" /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/review"
            element={
              <ProtectedRoute requiredRole="reviewer">
                <AppLayout><Placeholder name="ESCALATION REVIEW" /></AppLayout>
              </ProtectedRoute>
            }
          />
          <Route
            path="/audit"
            element={
              <ProtectedRoute>
                <AppLayout><Placeholder name="AUDIT LOG" /></AppLayout>
              </ProtectedRoute>
            }
          />

          {/* ── Catch-all ── */}
          <Route path="*" element={<NotFoundPage />} />

        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
