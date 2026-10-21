import { useRef } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Zap, Shield, Database,
         BarChart3, GitBranch, Cpu, ChevronRight } from 'lucide-react';
import HoloOrb from '../components/HoloOrb';
import '../auth.css';

const FEATURES = [
  {
    icon: '🔍',
    color: 'cyan',
    title: 'Constraint-Aware Retrieval',
    desc: 'CAR filters evidence by process state, timestamp validity and graph reachability. Score = α·sim + β·prox + γ·match before agents ever see it.',
  },
  {
    icon: '🛡️',
    color: 'violet',
    title: 'Symbolic Constraint Verifier',
    desc: 'SCV checks alignment cost, Declare automata, policy predicates and cross-agent conflicts. Issues a signed plan token before any write action executes.',
  },
  {
    icon: '🤖',
    color: 'gold',
    title: 'LangGraph Agent Team',
    desc: 'Coordinator → Planner → Critic → Executor. Each agent cites evidence provenance IDs. Confidence-gated escalation to human reviewers.',
  },
  {
    icon: '📊',
    color: 'green',
    title: 'WF-Adapt Benchmark',
    desc: 'Target of 840 annotated cases across 7 scenario types (S0–S6) over 4 BPI public event logs. Inter-annotator κ reported per constraint set.',
  },
  {
    icon: '🔗',
    color: 'blue',
    title: 'Hash-Chained Audit Log',
    desc: 'Every retrieval, plan, SCV verdict and action is appended to a SHA-256 hash chain. Full case replay. Tamper-evident by design.',
  },
  {
    icon: '📈',
    color: 'rose',
    title: '8-Config × 3-Model Study',
    desc: 'B0–B7 factorial study with 3 LLMs and 3 seeds each. McNemar, Friedman and mixed-effects logistic regression. Pre-registered analysis plan (H1–H4).',
  },
];

const STATS = [
  { value: '840', label: 'Target Cases' },
  { value: '8',   label: 'Configurations' },
  { value: '7',   label: 'Scenario Types' },
  { value: '3',   label: 'LLM Models' },
];

export default function HomePage() {
  return (
    <div className="auth-shell">
      {/* Particle canvas */}
      <canvas id="home-particles" className="particle-canvas" aria-hidden="true" />

      <div className="home-page">

        {/* ── Nav ─────────────────────────────────────── */}
        <nav className="home-nav">
          <Link to="/" className="home-nav-logo">
            <div className="home-nav-logo-mark">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="7.5" stroke="#00f5ff" strokeWidth="1"
                        strokeDasharray="4 2" />
                <circle cx="9" cy="9" r="3.5" fill="rgba(0,245,255,0.1)"
                        stroke="#b44dff" strokeWidth="0.8" />
                <circle cx="9" cy="9" r="1.5" fill="#00f5ff" />
              </svg>
            </div>
            <span className="home-nav-wordmark">CARMA</span>
          </Link>

          <div className="home-nav-links">
            <a href="#features"  className="home-nav-link">Features</a>
            <a href="#benchmark" className="home-nav-link">Benchmark</a>
            <Link to="/login" className="home-nav-link">Sign In</Link>
          </div>

          <div className="home-nav-actions">
            <Link to="/login"  className="btn btn-ghost"  style={{ fontSize:11, padding:'8px 18px' }}>Sign In</Link>
            <Link to="/signup" className="btn btn-solid"  style={{ fontSize:11, padding:'8px 18px' }}>
              Get Started <ArrowRight size={12} />
            </Link>
          </div>
        </nav>

        {/* ── Hero ─────────────────────────────────────── */}
        <section className="hero-section">
          <div className="hero-inner">

            <div className="hero-left">
              {/* Eyebrow */}
              <div className="hero-eyebrow">
                <span className="hero-eyebrow-dot" />
                Research Platform · CARMA v1.0
              </div>

              {/* Headline */}
              <h1 className="hero-headline">
                <span className="hero-headline-line1">Multi-Agent</span>
                <span className="hero-headline-line1">Workflow</span>
                <span className="hero-headline-line2">Adaptation</span>
              </h1>

              {/* Description */}
              <p className="hero-description">
                CARMA wraps an LLM agent team in two constraint layers —
                a <strong style={{ color:'var(--holo-cyan)' }}>Constraint-Aware Retriever</strong> and
                a <strong style={{ color:'var(--holo-violet)' }}>Symbolic Constraint Verifier</strong> —
                to make workflow adaptation measurably more reliable. Built on LangGraph,
                PM4Py, Declare4Py and public BPI event logs.
              </p>

              {/* CTA */}
              <div className="hero-cta">
                <Link to="/signup" className="btn btn-solid">
                  <Zap size={13} /> Start Research
                </Link>
                <Link to="/login" className="btn btn-primary">
                  Sign In <ChevronRight size={13} />
                </Link>
                <a href="#features" className="btn btn-ghost" style={{ fontSize: 11 }}>
                  <Cpu size={13} /> Architecture
                </a>
              </div>

              {/* Stats */}
              <div className="hero-stats">
                {STATS.map(s => (
                  <div key={s.label}>
                    <div className="hero-stat-value">{s.value}</div>
                    <div className="hero-stat-label">{s.label}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* Orb */}
            <div className="hero-right">
              <HoloOrb violationCount={0} />
            </div>

          </div>
        </section>

        {/* ── Section divider ──────────────────────────── */}
        <div style={{ padding:'0 48px' }}>
          <div className="section-divider">
            <div className="section-divider-line" />
            <div className="section-divider-label">Core Architecture</div>
            <div className="section-divider-line" />
          </div>
        </div>

        {/* ── Feature cards ────────────────────────────── */}
        <section className="features-section" id="features">
          <div className="section-header">
            <div className="holo-subtitle" style={{ marginBottom:10 }}>WHY CARMA</div>
            <h2 style={{ fontFamily:'var(--font-display)', fontSize:26, fontWeight:700,
                         color:'var(--text-primary)', letterSpacing:'-0.01em' }}>
              Two constraint layers. One empirical truth.
            </h2>
            <p style={{ color:'var(--text-muted)', fontSize:13, marginTop:10, maxWidth:520,
                        margin:'10px auto 0', lineHeight:1.7 }}>
              Each component addresses a specific research gap (G1–G5) identified
              in the 26-paper systematic review.
            </p>
          </div>

          <div className="features-grid">
            {FEATURES.map(f => (
              <div key={f.title}
                   className={`glass-card feature-card accent-${f.color}`}>
                <div className="feature-icon"
                     style={{ background:`rgba(0,0,0,0.3)` }}>
                  {f.icon}
                </div>
                <div>
                  <div className="feature-title">{f.title}</div>
                  <span className={`badge badge-${f.color}`} style={{ marginTop:4, fontSize:9 }}>
                    {f.color === 'cyan'   ? 'G1 · RQ1' :
                     f.color === 'violet' ? 'G2 · RQ2' :
                     f.color === 'gold'   ? 'G3 · RQ3' :
                     f.color === 'green'  ? 'G4 · O2'  :
                     f.color === 'blue'   ? 'G5 · O4'  : 'G4 · RQ4'}
                  </span>
                </div>
                <p className="feature-desc">{f.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── Benchmark CTA strip ──────────────────────── */}
        <section id="benchmark" style={{
          padding: '48px',
          position: 'relative',
          zIndex: 1,
        }}>
          <div className="glass-card" style={{
            maxWidth: 900,
            margin: '0 auto',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 32,
            padding: '32px 40px',
            borderColor: 'rgba(0,245,255,0.2)',
          }}>
            <div>
              <div className="holo-subtitle" style={{ marginBottom: 8 }}>WF-ADAPT BENCHMARK</div>
              <h3 style={{ fontFamily:'var(--font-display)', fontSize:20, fontWeight:700,
                           color:'var(--text-primary)', marginBottom:8 }}>
                Public · Reproducible · Pre-registered
              </h3>
              <p style={{ fontSize:12, color:'var(--text-muted)', lineHeight:1.7, maxWidth:480 }}>
                Target of 840 annotated cases across S0–S6 scenarios, built from the
                BPI 2017, 2019, 2020 and RTFM event logs. Annotation agreement (κ) is
                reported per constraint set, and the artifact bundle is released for
                academic reuse.
              </p>
            </div>
            <div style={{ flexShrink:0, display:'flex', flexDirection:'column', gap:10 }}>
              <Link to="/signup" className="btn btn-solid" style={{ whiteSpace:'nowrap' }}>
                <Database size={13} /> Access Benchmark
              </Link>
              <Link to="/login" className="btn btn-ghost" style={{ whiteSpace:'nowrap', fontSize:11 }}>
                <Shield size={12} /> Sign in to contribute
              </Link>
            </div>
          </div>
        </section>

        {/* ── Footer ──────────────────────────────────── */}
        <footer className="home-footer">
          <span>© 2026 CARMA Research Platform · MIT License</span>
          <span style={{ display:'flex', gap:24, alignItems:'center' }}>
            <Link to="/login" style={{ color:'var(--text-muted)', display:'flex', alignItems:'center',
                                      gap:4, textDecoration:'none' }}>
              <BarChart3 size={11} /> Research console
            </Link>
            <Link to="/signup" style={{ color:'var(--text-muted)', display:'flex', alignItems:'center',
                                       gap:4, textDecoration:'none' }}>
              <GitBranch size={11} /> Create an account
            </Link>
          </span>
        </footer>

      </div>
    </div>
  );
}
