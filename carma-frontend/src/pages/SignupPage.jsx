import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mail, Lock, Eye, EyeOff, User, ArrowLeft,
         CheckCircle, AlertCircle, Zap } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { authApi } from '../api/client';
import '../auth.css';

/* ── Password strength scorer ── */
function scorePassword(pw) {
  let score = 0;
  if (pw.length >= 8)                     score++;
  if (/[A-Z]/.test(pw))                  score++;
  if (/[0-9]/.test(pw))                  score++;
  if (/[^A-Za-z0-9]/.test(pw))          score++;
  return score; // 0–4
}

const STRENGTH_LABELS = ['', 'Weak', 'Fair', 'Good', 'Strong'];
const STRENGTH_COLORS = ['', 'weak', 'fair', 'good', 'strong'];

const ROLES = [
  { value:'researcher', label:'Researcher', icon:'🔬',
    desc:'Run experiments, build benchmarks' },
  { value:'reviewer',   label:'Reviewer',   icon:'🛡️',
    desc:'Review escalated cases, approve plans' },
  { value:'annotator',  label:'Annotator',  icon:'✏️',
    desc:'Annotate gold adaptations, compute κ' },
];

/** Extract a human-readable message from a DRF error response. */
function readApiError(err) {
  const data = err?.response?.data;
  if (!data) return err?.message ?? 'Unable to reach the CARMA API.';
  if (typeof data === 'string') return data;
  if (data.detail) return data.detail;
  const first = Object.entries(data)[0];
  if (!first) return 'Registration failed.';
  const [field, value] = first;
  const message = Array.isArray(value) ? value[0] : value;
  return `${field}: ${message}`;
}

export default function SignupPage() {
  const navigate = useNavigate();
  const login    = useAuthStore((s) => s.login);

  const [step, setStep]        = useState(1); // 1=details, 2=role, 3=success
  const [form, setForm]        = useState({
    firstName: '', lastName: '', email: '', password: '', confirm: '', role: 'researcher',
    agree: false,
  });
  const [showPass,  setShowPass]  = useState(false);
  const [showConf,  setShowConf]  = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [errors,    setErrors]    = useState({});
  const [apiError,  setApiError]  = useState('');

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const strength = scorePassword(form.password);

  /* ── Step 1 validation ── */
  const validateStep1 = () => {
    const e = {};
    if (!form.firstName.trim()) e.firstName = 'Required';
    if (!form.lastName.trim())  e.lastName  = 'Required';
    if (!form.email.includes('@')) e.email  = 'Valid email required';
    if (form.password.length < 8)  e.password = 'Min 8 characters';
    if (form.password !== form.confirm) e.confirm = 'Passwords do not match';
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const handleNext = () => {
    if (validateStep1()) setStep(2);
  };

  /* ── Submit ── */
  const handleSubmit = async () => {
    if (!form.agree) {
      setApiError('You must agree to the terms to continue.');
      return;
    }
    setApiError('');
    setLoading(true);

    try {
      const res = await authApi.register({
        email:      form.email,
        username:   form.email,
        password:   form.password,
        password2:  form.confirm,
        first_name: form.firstName,
        last_name:  form.lastName,
        role:       form.role,
      });
      const { user, access, refresh } = res.data;
      login(user, access, refresh);
      setStep(3);
    } catch (err) {
      setApiError(readApiError(err));
    } finally {
      setLoading(false);
    }
  };

  /* ── Render step 3 — Success ── */
  if (step === 3) {
    return (
      <div className="auth-shell">
        <div className="auth-page">
          <div className="auth-card">
            <div className="auth-card-glow" />
            <div className="auth-card-inner" style={{ textAlign:'center' }}>
              <div style={{
                width: 72, height: 72, borderRadius: '50%',
                background: 'rgba(0,255,136,0.1)',
                border: '2px solid rgba(0,255,136,0.4)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 24px',
                boxShadow: '0 0 40px rgba(0,255,136,0.2)',
                animation: 'orb-core-pulse 2s ease-in-out infinite',
              }}>
                <CheckCircle size={32} color="var(--holo-green)" />
              </div>

              <h2 className="auth-heading" style={{ marginBottom: 8 }}>
                Account Created!
              </h2>
              <p className="auth-subheading" style={{ marginBottom: 28 }}>
                Welcome to CARMA, <strong style={{ color:'var(--holo-cyan)' }}>
                {form.firstName}
                </strong>. Your <span className={`badge badge-${
                  form.role === 'admin' ? 'cyan' :
                  form.role === 'researcher' ? 'violet' :
                  form.role === 'reviewer' ? 'gold' : 'green'
                }`}>{form.role}</span> account is ready.
              </p>

              <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
                <button
                  className="btn btn-solid btn-auth"
                  onClick={() => navigate('/dashboard')}
                  id="go-to-dashboard-btn"
                >
                  <Zap size={13} /> Go to Dashboard
                </button>
                <Link to="/" className="btn btn-ghost btn-auth">
                  Back to Home
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-shell">
      <Link to="/" className="auth-back">
        <ArrowLeft size={12} /> Home
      </Link>

      <div className="auth-page">
        <div className="auth-card">
          <div className="auth-card-glow" />
          <div className="auth-card-inner">

            {/* Logo */}
            <div className="auth-logo">
              <div className="auth-logo-mark">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" stroke="#00f5ff" strokeWidth="1"
                          strokeDasharray="5 2.5" />
                  <circle cx="12" cy="12" r="5" fill="rgba(0,245,255,0.08)"
                          stroke="#b44dff" strokeWidth="1" />
                  <circle cx="12" cy="12" r="2" fill="#00f5ff" />
                </svg>
              </div>
              <span className="auth-logo-name">CARMA</span>
              <span className="auth-logo-tagline">Create your research account</span>
            </div>

            {/* Step indicator */}
            <div style={{ display:'flex', alignItems:'center', gap:0, marginBottom:24 }}>
              {[
                { n:1, label:'Details' },
                { n:2, label:'Role' },
              ].map((s, i) => (
                <div key={s.n} style={{ display:'flex', alignItems:'center', flex:1 }}>
                  <div style={{
                    display:'flex', flexDirection:'column', alignItems:'center', gap:4, flex:1,
                  }}>
                    <div style={{
                      width: 28, height: 28, borderRadius: '50%',
                      border: `1px solid ${step >= s.n ? 'var(--holo-cyan)' : 'var(--border-dim)'}`,
                      background: step > s.n
                        ? 'rgba(0,245,255,0.2)'
                        : step === s.n
                        ? 'rgba(0,245,255,0.1)'
                        : 'transparent',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 11,
                      fontFamily: 'var(--font-display)',
                      color: step >= s.n ? 'var(--holo-cyan)' : 'var(--text-muted)',
                      boxShadow: step === s.n ? '0 0 12px rgba(0,245,255,0.3)' : 'none',
                      transition: 'all 0.3s ease',
                    }}>
                      {step > s.n ? <CheckCircle size={13} /> : s.n}
                    </div>
                    <span style={{
                      fontSize: 9, fontFamily: 'var(--font-mono)',
                      letterSpacing: '0.1em', textTransform: 'uppercase',
                      color: step >= s.n ? 'var(--holo-cyan)' : 'var(--text-muted)',
                    }}>
                      {s.label}
                    </span>
                  </div>
                  {i < 1 && (
                    <div style={{
                      height: 1, flex: 1, marginBottom: 20,
                      background: step > s.n
                        ? 'linear-gradient(90deg,var(--holo-cyan),var(--holo-violet))'
                        : 'var(--border-dim)',
                      transition: 'background 0.4s ease',
                    }} />
                  )}
                </div>
              ))}
            </div>

            {/* API error */}
            {apiError && (
              <div className="auth-feedback error" style={{ marginBottom: 16 }}>
                <AlertCircle size={13} /> {apiError}
              </div>
            )}

            {/* ── STEP 1: Personal details ── */}
            {step === 1 && (
              <div className="auth-form">
                <div className="auth-field-row">
                  <div className="auth-field">
                    <label className="form-label" htmlFor="reg-first">First Name</label>
                    <div className="input-wrapper">
                      <User size={13} className="input-icon" />
                      <input
                        id="reg-first"
                        type="text"
                        className={`holo-input with-icon ${errors.firstName ? 'border-rose' : ''}`}
                        placeholder="Ada"
                        value={form.firstName}
                        onChange={(e) => set('firstName', e.target.value)}
                        autoComplete="given-name"
                      />
                    </div>
                    {errors.firstName && (
                      <span style={{ fontSize:10, color:'var(--holo-rose)', fontFamily:'var(--font-mono)' }}>
                        {errors.firstName}
                      </span>
                    )}
                  </div>

                  <div className="auth-field">
                    <label className="form-label" htmlFor="reg-last">Last Name</label>
                    <div className="input-wrapper">
                      <User size={13} className="input-icon" />
                      <input
                        id="reg-last"
                        type="text"
                        className="holo-input with-icon"
                        placeholder="Lovelace"
                        value={form.lastName}
                        onChange={(e) => set('lastName', e.target.value)}
                        autoComplete="family-name"
                      />
                    </div>
                    {errors.lastName && (
                      <span style={{ fontSize:10, color:'var(--holo-rose)', fontFamily:'var(--font-mono)' }}>
                        {errors.lastName}
                      </span>
                    )}
                  </div>
                </div>

                <div className="auth-field">
                  <label className="form-label" htmlFor="reg-email">Email Address</label>
                  <div className="input-wrapper">
                    <Mail size={14} className="input-icon" />
                    <input
                      id="reg-email"
                      type="email"
                      className="holo-input with-icon"
                      placeholder="ada@carma.ai"
                      value={form.email}
                      onChange={(e) => set('email', e.target.value)}
                      autoComplete="email"
                    />
                  </div>
                  {errors.email && (
                    <span style={{ fontSize:10, color:'var(--holo-rose)', fontFamily:'var(--font-mono)' }}>
                      {errors.email}
                    </span>
                  )}
                </div>

                <div className="auth-field">
                  <label className="form-label" htmlFor="reg-password">Password</label>
                  <div className="input-wrapper">
                    <Lock size={14} className="input-icon" />
                    <input
                      id="reg-password"
                      type={showPass ? 'text' : 'password'}
                      className="holo-input with-icon"
                      placeholder="Min 8 characters"
                      value={form.password}
                      onChange={(e) => set('password', e.target.value)}
                      autoComplete="new-password"
                    />
                    <button type="button" className="input-toggle"
                            onClick={() => setShowPass(v => !v)}>
                      {showPass ? <EyeOff size={13}/> : <Eye size={13}/>}
                    </button>
                  </div>

                  {/* Strength bars */}
                  {form.password && (
                    <div>
                      <div className="password-strength">
                        {[1,2,3,4].map(i => (
                          <div key={i} className={`strength-bar ${
                            i <= strength ? `active-${STRENGTH_COLORS[strength]}` : ''}`} />
                        ))}
                        <span className={`strength-label`}
                              style={{ color:
                                strength >= 4 ? 'var(--holo-green)'  :
                                strength >= 3 ? 'var(--holo-blue)'   :
                                strength >= 2 ? 'var(--holo-gold)'   :
                                               'var(--holo-rose)' }}>
                          {STRENGTH_LABELS[strength]}
                        </span>
                      </div>
                    </div>
                  )}

                  {errors.password && (
                    <span style={{ fontSize:10, color:'var(--holo-rose)', fontFamily:'var(--font-mono)' }}>
                      {errors.password}
                    </span>
                  )}
                </div>

                <div className="auth-field">
                  <label className="form-label" htmlFor="reg-confirm">Confirm Password</label>
                  <div className="input-wrapper">
                    <Lock size={14} className="input-icon" />
                    <input
                      id="reg-confirm"
                      type={showConf ? 'text' : 'password'}
                      className="holo-input with-icon"
                      placeholder="Repeat password"
                      value={form.confirm}
                      onChange={(e) => set('confirm', e.target.value)}
                      autoComplete="new-password"
                    />
                    <button type="button" className="input-toggle"
                            onClick={() => setShowConf(v => !v)}>
                      {showConf ? <EyeOff size={13}/> : <Eye size={13}/>}
                    </button>
                  </div>
                  {errors.confirm && (
                    <span style={{ fontSize:10, color:'var(--holo-rose)', fontFamily:'var(--font-mono)' }}>
                      {errors.confirm}
                    </span>
                  )}
                </div>

                <button
                  type="button"
                  className="btn btn-solid btn-auth"
                  onClick={handleNext}
                  id="signup-next-btn"
                >
                  Continue <ArrowLeft size={13} style={{ transform:'rotate(180deg)' }} />
                </button>
              </div>
            )}

            {/* ── STEP 2: Role selection + agree ── */}
            {step === 2 && (
              <div className="auth-form">
                <div>
                  <label className="form-label">Select Your Role</label>
                  <div className="role-selector" style={{ gridTemplateColumns:'repeat(2,1fr)' }}>
                    {ROLES.map(r => (
                      <div
                        key={r.value}
                        className={`role-option ${form.role === r.value ? 'selected' : ''}`}
                        onClick={() => set('role', r.value)}
                        id={`role-option-${r.value}`}
                      >
                        <span className="role-option-icon">{r.icon}</span>
                        <span className="role-option-label">{r.label}</span>
                        <span style={{ fontSize:9, color:'var(--text-muted)',
                                       lineHeight:1.4, textAlign:'center' }}>
                          {r.desc}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Terms checkbox */}
                <label className="auth-agree">
                  <input
                    type="checkbox"
                    id="agree-checkbox"
                    checked={form.agree}
                    onChange={(e) => set('agree', e.target.checked)}
                  />
                  I agree to the Terms of Service and the Research Data Policy.
                  All experiment data will be used solely for academic research.
                </label>

                <div style={{ display:'flex', gap:10 }}>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    style={{ flex:1, justifyContent:'center' }}
                    onClick={() => setStep(1)}
                  >
                    <ArrowLeft size={13} /> Back
                  </button>
                  <button
                    type="button"
                    className="btn btn-solid btn-auth"
                    style={{ flex:2 }}
                    onClick={handleSubmit}
                    disabled={loading || !form.agree}
                    id="signup-submit-btn"
                  >
                    {loading
                      ? <><span className="spinner" /> Creating…</>
                      : <><Zap size={13} /> Create Account</>
                    }
                  </button>
                </div>
              </div>
            )}

            {/* Switch to login */}
            <div className="auth-switch">
              Already have an account?{' '}
              <Link to="/login">Sign in</Link>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
