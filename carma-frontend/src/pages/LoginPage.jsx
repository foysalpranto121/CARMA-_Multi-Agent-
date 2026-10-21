import { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { Mail, Lock, Eye, EyeOff, ArrowLeft, Zap, AlertCircle } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../api/client';
import HoloOrb from '../components/HoloOrb';
import '../auth.css';

/** Extract a human-readable message from a DRF error response. */
function readApiError(err) {
  const data = err?.response?.data;
  if (!data) return err?.message ?? 'Unable to reach the CARMA API.';
  if (typeof data === 'string') return data;
  if (data.detail) return data.detail;
  const first = Object.entries(data)[0];
  if (!first) return 'Login failed.';
  const [field, value] = first;
  const message = Array.isArray(value) ? value[0] : value;
  return `${field}: ${message}`;
}

export default function LoginPage() {
  const navigate   = useNavigate();
  const location   = useLocation();
  const login      = useAuthStore((s) => s.login);
  const from       = location.state?.from ?? '/dashboard';

  const [email,     setEmail]     = useState('');
  const [password,  setPassword]  = useState('');
  const [showPass,  setShowPass]  = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState('');
  const [activeNode,setActiveNode]= useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!email || !password) { setError('Please fill in all fields.'); return; }

    setLoading(true);
    try {
      const res = await authApi.login(email, password);
      const { access, refresh, user } = res.data;
      login(user, access, refresh);
      navigate(from, { replace: true });
    } catch (err) {
      setError(readApiError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-shell">

      {/* Back to home */}
      <Link to="/" className="auth-back">
        <ArrowLeft size={12} /> Home
      </Link>

      {/* Ambient orb — background decoration only */}
      <div style={{
        position: 'fixed', left: '6%', top: '50%', transform: 'translateY(-50%)',
        opacity: 0.35, pointerEvents: 'none',
      }}>
        <HoloOrb onNodeClick={setActiveNode} activeNode={activeNode} />
      </div>

      <div className="auth-page">
        <div className="auth-card">

          {/* Glow border */}
          <div className="auth-card-glow" />

          <div className="auth-card-inner">

            {/* Logo */}
            <div className="auth-logo">
              <div className="auth-logo-mark">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="#00f5ff" strokeWidth="1"
                          strokeDasharray="5 2.5" />
                  <circle cx="12" cy="12" r="5"  fill="rgba(0,245,255,0.08)"
                          stroke="#b44dff" strokeWidth="1" />
                  <circle cx="12" cy="12" r="2"  fill="#00f5ff" />
                </svg>
              </div>
              <span className="auth-logo-name">CARMA</span>
              <span className="auth-logo-tagline">
                Constraint-Aware Multi-Agent Research Platform
              </span>
            </div>

            <h2 className="auth-heading">Welcome Back</h2>
            <p className="auth-subheading">
              Sign in to access your experiments, benchmarks and results.
            </p>

            {/* Error feedback */}
            {error && (
              <div className="auth-feedback error" style={{ marginBottom: 16 }}>
                <AlertCircle size={13} /> {error}
              </div>
            )}

            {/* Form */}
            <form className="auth-form" onSubmit={handleSubmit} noValidate>

              {/* Email */}
              <div className="auth-field">
                <label className="form-label" htmlFor="login-email">Email Address</label>
                <div className="input-wrapper">
                  <Mail size={14} className="input-icon" />
                  <input
                    id="login-email"
                    type="email"
                    className="holo-input with-icon"
                    placeholder="researcher@carma.ai"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="email"
                    required
                  />
                </div>
              </div>

              {/* Password */}
              <div className="auth-field">
                <label className="form-label" htmlFor="login-password">Password</label>
                <div className="input-wrapper">
                  <Lock size={14} className="input-icon" />
                  <input
                    id="login-password"
                    type={showPass ? 'text' : 'password'}
                    className="holo-input with-icon"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                    required
                  />
                  <button
                    type="button"
                    className="input-toggle"
                    onClick={() => setShowPass(v => !v)}
                    aria-label={showPass ? 'Hide password' : 'Show password'}
                  >
                    {showPass ? <EyeOff size={13} /> : <Eye size={13} />}
                  </button>
                </div>
              </div>

              {/* Submit */}
              <button
                type="submit"
                className="btn btn-solid btn-auth"
                disabled={loading}
                id="login-submit-btn"
              >
                {loading
                  ? <><span className="spinner" /> Authenticating…</>
                  : <><Zap size={13} /> Sign In</>
                }
              </button>
            </form>

            {/* Switch to signup */}
            <div className="auth-switch">
              Don't have an account?{' '}
              <Link to="/signup">Create account</Link>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
