import { useState, useRef } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { Mail, Lock, Eye, EyeOff, ArrowLeft, Zap, AlertCircle } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../api/client';
import HoloOrb from '../components/HoloOrb';
import '../auth.css';

/* ── Mock login for offline development ── */
const MOCK_USERS = {
  'admin@carma.ai':      { password: 'carma123', role: 'admin',      firstName: 'Admin' },
  'researcher@carma.ai': { password: 'carma123', role: 'researcher',  firstName: 'Researcher' },
  'reviewer@carma.ai':   { password: 'carma123', role: 'reviewer',   firstName: 'Reviewer' },
};

function mockLogin(email, password) {
  const user = MOCK_USERS[email];
  if (!user || user.password !== password) throw new Error('Invalid credentials');
  return {
    user:    { id: '1', username: email, email, role: user.role, firstName: user.firstName },
    access:  'mock-access-token',
    refresh: 'mock-refresh-token',
  };
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
      /* Try real API first, fall back to mock */
      let data;
      try {
        const res = await authApi.login(email, password);
        data = res.data;
      } catch {
        data = mockLogin(email, password);
      }
      login(data.user, data.access, data.refresh);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message ?? 'Invalid email or password.');
    } finally {
      setLoading(false);
    }
  };

  /* Quick-fill demo credentials */
  const fillDemo = (role) => {
    const map = {
      admin:      'admin@carma.ai',
      researcher: 'researcher@carma.ai',
      reviewer:   'reviewer@carma.ai',
    };
    setEmail(map[role]);
    setPassword('carma123');
    setError('');
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
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                  <label className="form-label" htmlFor="login-password">Password</label>
                  <a href="#" style={{ fontSize:10, color:'var(--holo-cyan)', textDecoration:'none',
                                       fontFamily:'var(--font-mono)', letterSpacing:'0.05em' }}>
                    Forgot password?
                  </a>
                </div>
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

            {/* Demo credentials */}
            <div className="auth-divider" style={{ marginTop: 20 }}>
              <div className="auth-divider-line" />
              <span className="auth-divider-text">Demo Access</span>
              <div className="auth-divider-line" />
            </div>

            <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:8 }}>
              {[
                { role:'admin',      label:'Admin',      color:'cyan',   icon:'👑' },
                { role:'researcher', label:'Researcher', color:'violet', icon:'🔬' },
                { role:'reviewer',   label:'Reviewer',   color:'gold',   icon:'🛡️' },
              ].map(d => (
                <button
                  key={d.role}
                  type="button"
                  className={`role-option`}
                  onClick={() => fillDemo(d.role)}
                  id={`demo-${d.role}-btn`}
                  title={`Fill demo credentials for ${d.label}`}
                >
                  <span className="role-option-icon">{d.icon}</span>
                  <span className={`role-option-label`}
                        style={{ color:`var(--holo-${d.color})` }}>
                    {d.label}
                  </span>
                </button>
              ))}
            </div>

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
