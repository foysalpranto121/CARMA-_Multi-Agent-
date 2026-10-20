import { Link } from 'react-router-dom';
import HoloOrb from '../components/HoloOrb';

export default function NotFoundPage() {
  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg-void)',
      gap: 32,
      padding: 40,
      position: 'relative',
    }}>
      {/* Background grid */}
      <div style={{
        position: 'fixed', inset: 0,
        backgroundImage:
          'linear-gradient(rgba(0,245,255,0.03) 1px, transparent 1px),' +
          'linear-gradient(90deg, rgba(0,245,255,0.03) 1px, transparent 1px)',
        backgroundSize: '52px 52px',
        pointerEvents: 'none',
      }} />

      {/* Dim orb */}
      <div style={{ opacity: 0.4 }}>
        <HoloOrb violationCount={404} />
      </div>

      <div style={{ textAlign: 'center', position: 'relative', zIndex: 1 }}>
        <div style={{
          fontFamily: 'var(--font-display)',
          fontSize: 96,
          fontWeight: 900,
          lineHeight: 1,
          background: 'linear-gradient(135deg, var(--holo-cyan), var(--holo-violet))',
          WebkitBackgroundClip: 'text',
          WebkitTextFillColor: 'transparent',
          backgroundClip: 'text',
          marginBottom: 16,
          animation: 'flicker 5s infinite',
        }}>
          404
        </div>

        <div className="holo-subtitle" style={{ marginBottom: 12 }}>
          SIGNAL LOST — TRAJECTORY NOT FOUND
        </div>

        <p style={{
          color: 'var(--text-secondary)', fontSize: 14,
          lineHeight: 1.7, maxWidth: 380, margin: '0 auto 28px',
        }}>
          The process path you requested does not exist in the constraint graph.
          The system cannot reach this state from the current prefix trace.
        </p>

        <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
          <Link to="/"          className="btn btn-solid">↖ Home</Link>
          <Link to="/dashboard" className="btn btn-primary">Dashboard</Link>
        </div>
      </div>
    </div>
  );
}
