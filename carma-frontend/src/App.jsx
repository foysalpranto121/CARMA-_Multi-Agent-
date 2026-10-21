import './index.css';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

/* Auth */
import { PublicRoute, ProtectedRoute } from './components/AuthGuard';

/* Public pages */
import HomePage   from './pages/HomePage';
import LoginPage  from './pages/LoginPage';
import SignupPage from './pages/SignupPage';

/* App shell (authenticated layout) */
import Sidebar    from './components/Sidebar';
import TopBar     from './components/TopBar';
import Dashboard     from './pages/Dashboard';
import ProcessesPage from './pages/ProcessesPage';
import BenchmarkPage from './pages/BenchmarkPage';
import ExperimentsPage    from './pages/ExperimentsPage';
import ExperimentNewPage  from './pages/ExperimentNewPage';
import ExperimentDetailPage from './pages/ExperimentDetailPage';
import MetricsPage from './pages/MetricsPage';
import ReviewPage  from './pages/ReviewPage';
import AuditPage   from './pages/AuditPage';
import NotFoundPage from './pages/NotFoundPage';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

/* ── Authenticated layout wrapper ── */
function AppLayout({ children }) {
  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-content">
        <TopBar />
        {children}
      </div>
    </div>
  );
}

/* Convenience wrapper: a protected route inside the app shell. */
function Shell({ roles, children }) {
  return (
    <ProtectedRoute requiredRole={roles}>
      <AppLayout>{children}</AppLayout>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>

          {/* ── PUBLIC routes (redirect to /dashboard if already logged in) ── */}
          <Route path="/"    element={<PublicRoute><HomePage /></PublicRoute>} />
          <Route path="/login"  element={<PublicRoute><LoginPage /></PublicRoute>} />
          <Route path="/signup" element={<PublicRoute><SignupPage /></PublicRoute>} />

          {/* ── PROTECTED routes (redirect to /login if not authenticated) ── */}
          <Route path="/dashboard" element={<Shell><Dashboard /></Shell>} />

          <Route path="/processes" element={<Shell roles={['researcher']}>
            <ProcessesPage />
          </Shell>} />

          <Route path="/benchmark" element={<Shell>
            <BenchmarkPage />
          </Shell>} />

          <Route path="/experiments" element={<Shell>
            <ExperimentsPage />
          </Shell>} />

          <Route path="/experiments/new" element={<Shell roles={['researcher']}>
            <ExperimentNewPage />
          </Shell>} />

          <Route path="/experiments/:id" element={<Shell>
            <ExperimentDetailPage />
          </Shell>} />

          <Route path="/metrics" element={<Shell roles={['researcher']}>
            <MetricsPage />
          </Shell>} />

          <Route path="/review" element={<Shell roles={['reviewer']}>
            <ReviewPage />
          </Shell>} />

          <Route path="/audit" element={<Shell roles={['researcher']}>
            <AuditPage />
          </Shell>} />

          {/* ── Catch-all ── */}
          <Route path="*" element={<NotFoundPage />} />

        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
