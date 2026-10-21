import { useState } from 'react';
import {
  LayoutDashboard, FlaskConical, Database, BarChart3,
  ShieldAlert, ScrollText, ChevronRight, ChevronLeft,
  Cpu, LogOut
} from 'lucide-react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuthStore, hasRole } from '../store/authStore';

const NAV_ITEMS = [
  { to: '/dashboard',   icon: LayoutDashboard, label: 'Dashboard',   tip: 'Dashboard',    roles: null },
  { to: '/processes',   icon: Cpu,              label: 'Processes',   tip: 'Process Frames', roles: ['researcher'] },
  { to: '/benchmark',   icon: Database,         label: 'Benchmark',   tip: 'WF-Adapt Benchmark', roles: null },
  { to: '/experiments', icon: FlaskConical,     label: 'Experiments', tip: 'Experiment Runs', roles: null },
  { to: '/metrics',     icon: BarChart3,        label: 'Metrics',     tip: 'Results & Statistics', roles: ['researcher'] },
  { to: '/review',      icon: ShieldAlert,      label: 'Review',      tip: 'Escalation Queue', roles: ['reviewer'] },
  { to: '/audit',       icon: ScrollText,       label: 'Audit',       tip: 'Audit Log', roles: ['researcher'] },
];

const ROLE_COLOR = {
  admin:      'var(--holo-cyan)',
  researcher: 'var(--holo-violet)',
  reviewer:   'var(--holo-gold)',
  annotator:  'var(--holo-green)',
};

export default function Sidebar() {
  const [expanded, setExpanded] = useState(false);
  const { user, logout }        = useAuthStore();
  const navigate                = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/', { replace: true });
  };

  const visibleItems = NAV_ITEMS.filter(
    (item) => hasRole(user?.role, item.roles),
  );

  return (
    <nav
      className={`sidebar ${expanded ? 'expanded' : ''}`}
      aria-label="Main navigation"
    >
      {/* ── Logo / toggle ── */}
      <div
        className="sidebar-logo"
        onClick={() => setExpanded(e => !e)}
        title="Toggle sidebar"
        role="button"
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && setExpanded(v => !v)}
      >
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <circle cx="10" cy="10" r="8"  stroke="#00f5ff" strokeWidth="1" strokeDasharray="4 2" />
          <circle cx="10" cy="10" r="4"  fill="rgba(0,245,255,0.15)" stroke="#b44dff" strokeWidth="1" />
          <circle cx="10" cy="10" r="1.8" fill="#00f5ff" />
        </svg>
        <span className="sidebar-logo-text">CARMA</span>
      </div>

      {/* ── Nav links ── */}
      <div className="sidebar-nav">
        {visibleItems.map(({ to, icon: Icon, label, tip }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
          >
            <Icon size={16} strokeWidth={1.5} aria-hidden="true" />
            <span className="nav-label">{label}</span>
            {!expanded && <span className="nav-tooltip">{tip}</span>}
          </NavLink>
        ))}
      </div>

      {/* ── User pill ── */}
      {user && (
        <div style={{
          width: expanded ? '100%' : 44,
          padding: expanded ? '8px 10px' : '8px 0',
          marginBottom: 8,
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--border-dim)',
          background: 'rgba(0,0,0,0.2)',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          overflow: 'hidden',
          transition: 'all var(--duration-slow) var(--ease-out-expo)',
          justifyContent: expanded ? 'flex-start' : 'center',
        }}>
          {/* Avatar */}
          <div style={{
            width: 28, height: 28, flexShrink: 0,
            borderRadius: '50%',
            background: `linear-gradient(135deg, ${ROLE_COLOR[user.role] ?? 'var(--holo-cyan)'}, var(--bg-elevated))`,
            border: `1px solid ${ROLE_COLOR[user.role] ?? 'var(--border-mid)'}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 11, fontWeight: 700, color: '#fff',
            fontFamily: 'var(--font-display)',
            boxShadow: `0 0 10px ${ROLE_COLOR[user.role] ?? 'var(--holo-cyan)'}33`,
          }}>
            {(user.firstName?.[0] ?? user.username?.[0] ?? '?').toUpperCase()}
          </div>

          {/* Name + role (only when expanded) */}
          {expanded && (
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                fontSize: 11, fontWeight: 600, color: 'var(--text-primary)',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {user.fullName ?? user.username}
              </div>
              <div style={{
                fontSize: 9, fontFamily: 'var(--font-mono)', letterSpacing: '0.1em',
                textTransform: 'uppercase',
                color: ROLE_COLOR[user.role] ?? 'var(--holo-cyan)',
              }}>
                {user.role}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Logout button ── */}
      <button
        className="nav-item"
        onClick={handleLogout}
        title="Sign out"
        style={{
          width: expanded ? '100%' : 44,
          justifyContent: expanded ? 'flex-start' : 'center',
          color: 'var(--text-muted)',
          marginBottom: 4,
          background: 'none',
          cursor: 'pointer',
          border: '1px solid transparent',
        }}
        id="logout-btn"
      >
        <LogOut size={15} strokeWidth={1.5} />
        <span className="nav-label">Sign Out</span>
        {!expanded && <span className="nav-tooltip">Sign Out</span>}
      </button>

      {/* ── Collapse toggle ── */}
      <button
        className="sidebar-toggle"
        onClick={() => setExpanded(e => !e)}
        aria-label={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
      >
        {expanded ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
      </button>
    </nav>
  );
}
