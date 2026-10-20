import { Bell, Wifi, WifiOff, User } from 'lucide-react';
import { useLocation, Link } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

const PAGE_TITLES = {
  '/dashboard':          { title: 'DASHBOARD',   sub: 'System Overview' },
  '/processes':          { title: 'PROCESSES',   sub: 'Process Frames & Constraints' },
  '/benchmark':          { title: 'WF-ADAPT',    sub: 'Benchmark · 840 Cases · 7 Scenarios' },
  '/experiments':        { title: 'EXPERIMENTS', sub: '8 Configurations · 3 Models · 3 Seeds' },
  '/experiments/new':    { title: 'NEW RUN',     sub: 'Configure Experiment' },
  '/metrics':            { title: 'METRICS',     sub: 'Statistical Analysis & Results' },
  '/review':             { title: 'REVIEW',      sub: 'Human Escalation Queue' },
  '/audit':              { title: 'AUDIT LOG',   sub: 'Hash-Chained Trace Replay' },
};

const ROLE_COLOR = {
  admin:      'var(--holo-cyan)',
  researcher: 'var(--holo-violet)',
  reviewer:   'var(--holo-gold)',
  annotator:  'var(--holo-green)',
};

/* Live clock component */
function LiveClock() {
  const [time, setTime] = useState(new Date().toISOString().slice(0,19).replace('T',' ') + ' UTC');
  useEffect(() => {
    const t = setInterval(() =>
      setTime(new Date().toISOString().slice(0,19).replace('T',' ') + ' UTC'), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <span style={{
      fontFamily: 'var(--font-mono)', fontSize: 10,
      color: 'var(--text-muted)', letterSpacing: '0.04em',
    }}>
      {time}
    </span>
  );
}

import { useState, useEffect } from 'react';

export default function TopBar({ systemOnline = true }) {
  const location = useLocation();
  const { user } = useAuthStore();
  const page     = PAGE_TITLES[location.pathname] ?? { title: 'CARMA', sub: 'Research Platform' };

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div>
          <div className="page-title">{page.title}</div>
          <div className="breadcrumb" style={{ marginTop: 1 }}>
            CARMA / {page.sub}
          </div>
        </div>
      </div>

      <div className="topbar-right">
        {/* Live clock */}
        <LiveClock />

        {/* System status */}
        <div className="system-status">
          {systemOnline
            ? <>
                <div className="status-dot" />
                <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)' }}>ONLINE</span>
                <Wifi size={11} color="var(--holo-green)" />
              </>
            : <>
                <div className="status-dot error" />
                <span style={{ fontSize: 10 }}>OFFLINE</span>
                <WifiOff size={11} color="var(--holo-rose)" />
              </>
          }
        </div>

        {/* Notifications bell */}
        <button
          className="btn btn-ghost btn-icon"
          aria-label="Notifications"
          style={{ position: 'relative' }}
        >
          <Bell size={14} />
          <span style={{
            position: 'absolute', top: 6, right: 6,
            width: 5, height: 5, borderRadius: '50%',
            background: 'var(--holo-rose)',
            boxShadow: '0 0 6px var(--holo-rose)',
          }} />
        </button>

        {/* User chip */}
        {user && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '4px 12px 4px 6px',
            borderRadius: 'var(--radius-full)',
            border: '1px solid var(--border-dim)',
            background: 'rgba(0,0,0,0.25)',
            cursor: 'default',
          }}>
            <div style={{
              width: 22, height: 22, borderRadius: '50%',
              background: `linear-gradient(135deg, ${ROLE_COLOR[user.role] ?? 'var(--holo-cyan)'}, var(--bg-elevated))`,
              border: `1px solid ${ROLE_COLOR[user.role] ?? 'var(--border-mid)'}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 9, fontWeight: 700, color: '#fff',
              fontFamily: 'var(--font-display)',
            }}>
              {(user.firstName?.[0] ?? user.username?.[0] ?? '?').toUpperCase()}
            </div>
            <div>
              <div style={{
                fontSize: 11, fontWeight: 600, color: 'var(--text-primary)',
                lineHeight: 1.1,
              }}>
                {user.firstName ?? user.username}
              </div>
              <div style={{
                fontSize: 8, fontFamily: 'var(--font-mono)',
                letterSpacing: '0.1em', textTransform: 'uppercase',
                color: ROLE_COLOR[user.role] ?? 'var(--holo-cyan)',
              }}>
                {user.role}
              </div>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
