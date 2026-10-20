import { useEffect, useRef, useState, useCallback } from 'react';

/* ─── Particle canvas hook ─────────────────────────────────── */
function useParticleCanvas(canvasRef) {
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let animId;

    const resize = () => {
      canvas.width  = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    resize();
    window.addEventListener('resize', resize);

    const COLORS = ['#00f5ff', '#b44dff', '#ffd700', '#00ff88'];
    const particles = Array.from({ length: 80 }, () => ({
      x: Math.random() * window.innerWidth,
      y: Math.random() * window.innerHeight,
      vx: (Math.random() - 0.5) * 0.3,
      vy: -Math.random() * 0.6 - 0.1,
      size: Math.random() * 1.5 + 0.3,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
      alpha: Math.random(),
      alphaSpeed: (Math.random() * 0.008 + 0.002) * (Math.random() < 0.5 ? 1 : -1),
      drift: (Math.random() - 0.5) * 0.002,
    }));

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach(p => {
        p.x  += p.vx + Math.sin(Date.now() * p.drift) * 0.3;
        p.y  += p.vy;
        p.alpha += p.alphaSpeed;
        if (p.alpha <= 0 || p.alpha >= 1) p.alphaSpeed *= -1;
        if (p.y < -10) { p.y = canvas.height + 10; p.x = Math.random() * canvas.width; }

        ctx.save();
        ctx.globalAlpha = Math.max(0, Math.min(1, p.alpha)) * 0.7;
        ctx.shadowBlur  = 8;
        ctx.shadowColor = p.color;
        ctx.fillStyle   = p.color;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      });
      animId = requestAnimationFrame(draw);
    };
    draw();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, [canvasRef]);
}

/* ─── Data node positions around the orb ───────────────────── */
const DATA_NODES = [
  { id: 'car',   label: 'CAR',  cls: 'node-car',   top: '8%',  left: '50%',  transform: 'translateX(-50%)' },
  { id: 'scv',   label: 'SCV',  cls: 'node-scv',   top: '50%', right: '4%',  transform: 'translateY(-50%)' },
  { id: 'plan',  label: 'PLN',  cls: 'node-plan',  bottom:'8%',left: '50%',  transform: 'translateX(-50%)' },
  { id: 'exec',  label: 'EXE',  cls: 'node-exec',  top: '50%', left: '4%',   transform: 'translateY(-50%)' },
];

const NODE_TOOLTIP = {
  car:  'Constraint-Aware Retriever — filters evidence by process state',
  scv:  'Symbolic Constraint Verifier — gates write actions with plan token',
  plan: 'LangGraph Planner — produces schema-validated adaptation plans',
  exec: 'ReAct Executor — least-privilege MCP tool agent',
};

/* ─── Orb Component ─────────────────────────────────────────── */
export default function HoloOrb({ onNodeClick, activeNode, violationCount = 0 }) {
  const canvasRef   = useRef(null);
  const orbRef      = useRef(null);
  const [hovered, setHovered]     = useState(false);
  const [tilt, setTilt]           = useState({ x: 0, y: 0 });
  const [activeTooltip, setActiveTooltip] = useState(null);
  const [ripples, setRipples]     = useState([]);

  useParticleCanvas(canvasRef);

  /* Mouse tilt effect */
  const handleMouseMove = useCallback((e) => {
    if (!orbRef.current) return;
    const rect = orbRef.current.getBoundingClientRect();
    const cx   = rect.left + rect.width  / 2;
    const cy   = rect.top  + rect.height / 2;
    const dx   = (e.clientX - cx) / (rect.width  / 2);
    const dy   = (e.clientY - cy) / (rect.height / 2);
    setTilt({ x: dy * -12, y: dx * 12 });
  }, []);

  const handleMouseLeave = useCallback(() => {
    setHovered(false);
    setTilt({ x: 0, y: 0 });
  }, []);

  /* Click ripple */
  const handleOrbClick = useCallback((e) => {
    const id = Date.now();
    setRipples(r => [...r, id]);
    setTimeout(() => setRipples(r => r.filter(x => x !== id)), 2000);
  }, []);

  return (
    <>
      {/* Global particle canvas */}
      <canvas ref={canvasRef} className="particle-canvas" aria-hidden="true" />

      {/* Orb stage */}
      <div
        ref={orbRef}
        className="orb-stage"
        onMouseMove={handleMouseMove}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={handleMouseLeave}
        onClick={handleOrbClick}
        role="button"
        aria-label="CARMA holographic orb — click to pulse"
        tabIndex={0}
      >
        {/* Ambient glow */}
        <div className="orb-ambient" />

        {/* Rotating rings */}
        <div className="orb-ring orb-ring-1" />
        <div className="orb-ring orb-ring-2" />
        <div className="orb-ring orb-ring-3" />

        {/* Pulse rings (on hover) */}
        <div className="orb-pulse-ring" />
        <div className="orb-pulse-ring" />
        <div className="orb-pulse-ring" />

        {/* Core sphere */}
        <div
          className="orb-core"
          style={{
            transform: `
              perspective(600px)
              rotateX(${tilt.x}deg)
              rotateY(${tilt.y}deg)
              ${hovered ? 'scale(1.07)' : 'scale(1)'}
            `,
            transition: hovered
              ? 'transform 0.1s ease-out'
              : 'transform 0.6s cubic-bezier(0.16,1,0.3,1)',
          }}
        >
          {/* Scan line */}
          <div className="orb-scanline" />

          {/* Violation alert indicator */}
          {violationCount > 0 && (
            <div style={{
              position: 'absolute',
              top: '16%', right: '16%',
              width: 14, height: 14,
              borderRadius: '50%',
              background: '#ff3d71',
              boxShadow: '0 0 12px #ff3d71, 0 0 24px #ff3d71',
              border: '1px solid rgba(255,255,255,0.4)',
              zIndex: 10,
              fontSize: 7,
              fontFamily: 'var(--font-mono)',
              fontWeight: 700,
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              {violationCount}
            </div>
          )}
        </div>

        {/* Click ripples */}
        {ripples.map(id => (
          <div
            key={id}
            style={{
              position: 'absolute',
              width: 200, height: 200,
              borderRadius: '50%',
              border: '1px solid rgba(0,245,255,0.6)',
              animation: 'ring-expand 1.5s ease-out forwards',
              pointerEvents: 'none',
            }}
          />
        ))}

        {/* Orbit data nodes */}
        {DATA_NODES.map(node => (
          <div
            key={node.id}
            className={`orb-data-node ${node.cls} ${activeNode === node.id ? 'active' : ''}`}
            style={{
              position: 'absolute',
              top: node.top, bottom: node.bottom,
              left: node.left, right: node.right,
              transform: node.transform,
              outline: activeNode === node.id
                ? '2px solid currentColor'
                : 'none',
            }}
            onClick={(e) => { e.stopPropagation(); onNodeClick?.(node.id); }}
            onMouseEnter={() => setActiveTooltip(node.id)}
            onMouseLeave={() => setActiveTooltip(null)}
            title={NODE_TOOLTIP[node.id]}
          >
            {node.label}

            {/* Tooltip */}
            {activeTooltip === node.id && (
              <div style={{
                position: 'absolute',
                top: '110%', left: '50%',
                transform: 'translateX(-50%)',
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border-mid)',
                borderRadius: 'var(--radius-sm)',
                padding: '6px 10px',
                fontSize: 9,
                fontFamily: 'var(--font-mono)',
                color: 'var(--text-secondary)',
                whiteSpace: 'nowrap',
                zIndex: 999,
                pointerEvents: 'none',
                boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
                marginTop: 4,
              }}>
                {NODE_TOOLTIP[node.id]}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
