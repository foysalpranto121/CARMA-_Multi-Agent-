import { useState, useEffect, useRef } from 'react';
import HoloOrb from '../components/HoloOrb';
import {
  Activity, Zap, ShieldCheck, ShieldX, Clock, TrendingUp,
  TrendingDown, TriangleAlert, CheckCircle, ArrowRight, Cpu,
  GitBranch, FlaskConical
} from 'lucide-react';

/* ── Animated counter hook ──────────────────────────────────── */
function useCountUp(target, duration = 1200) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    let start = null;
    const step = (ts) => {
      if (!start) start = ts;
      const progress = Math.min((ts - start) / duration, 1);
      const eased    = 1 - Math.pow(1 - progress, 3);
      setVal(Math.floor(eased * target));
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }, [target, duration]);
  return val;
}

/* ── KPI Tile ───────────────────────────────────────────────── */
function KpiTile({ label, value, unit = '', color, delta, deltaDir, icon: Icon, delay = 0 }) {
  const animated = useCountUp(typeof value === 'number' ? value : 0);
  return (
    <div className="glass-card kpi-tile" style={{ animationDelay: `${delay}ms` }}>
      <div className="flex items-center justify-between mb-md">
        <span className="kpi-label">{label}</span>
        {Icon && (
          <div style={{
            width: 28, height: 28, borderRadius: 'var(--radius-sm)',
            background: `rgba(var(--raw-${color},0),0.1)`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            border: '1px solid var(--border-dim)',
          }}>
            <Icon size={13} color={`var(--holo-${color})`} />
          </div>
        )}
      </div>
      <div className={`kpi-value ${color}`}>
        {typeof value === 'number' ? animated : value}{unit}
      </div>
      {delta && (
        <div className={`kpi-delta ${deltaDir}`} style={{ marginTop: 6 }}>
          {deltaDir === 'up'
            ? <TrendingUp size={10} />
            : <TrendingDown size={10} />
          }
          {delta}
        </div>
      )}
    </div>
  );
}

/* ── Config row ─────────────────────────────────────────────── */
const CONFIGS = [
  { code:'B0', name:'Rule-Based',       car:false, scv:false, agents:0,  cvr:'4.2%',  tsr:'91.0%', color:'gold' },
  { code:'B1', name:'Single LLM',       car:false, scv:false, agents:1,  cvr:'38.1%', tsr:'51.3%', color:'rose' },
  { code:'B2', name:'Single+VecRAG',    car:false, scv:false, agents:1,  cvr:'29.4%', tsr:'60.7%', color:'rose' },
  { code:'B3', name:'Single+GraphRAG',  car:false, scv:false, agents:1,  cvr:'24.8%', tsr:'65.1%', color:'violet' },
  { code:'B4', name:'MAS+VecRAG',       car:false, scv:false, agents:4,  cvr:'22.3%', tsr:'68.4%', color:'violet' },
  { code:'B5', name:'MAS+CAR',          car:true,  scv:false, agents:4,  cvr:'15.7%', tsr:'74.2%', color:'blue' },
  { code:'B6', name:'MAS+SCV',          car:false, scv:true,  agents:4,  cvr:'12.4%', tsr:'79.6%', color:'cyan' },
  { code:'B7', name:'CARMA (Full)',      car:true,  scv:true,  agents:4,  cvr:'7.1%',  tsr:'87.3%', color:'green' },
];

/* ── Simulated log entries ─────────────────────────────────── */
const MOCK_LOGS = [
  { time:'19:07:42', type:'retrieval', msg:'CAR: retrieved 10 docs [stage=credit_check, PRV-4A2F..+9]' },
  { time:'19:07:43', type:'plan',      msg:'Planner → plan_id=e8b1 confidence=0.83 activities=[verify_income, reassign_officer]' },
  { time:'19:07:44', type:'scv',       msg:'SCV: checking alignment cost... Declare automata (response A→B) ✓' },
  { time:'19:07:44', type:'scv',       msg:'SCV: policy pred [amount<10000 ∧ role=officer] ✓ — TOKEN ISSUED' },
  { time:'19:07:45', type:'action',    msg:'Executor: WRITE verify_income(case_id=BPI17-4421) [token=e8b1.3f7a]' },
  { time:'19:07:46', type:'plan',      msg:'Planner → plan_id=c3d9 confidence=0.41 — repair round 1/3' },
  { time:'19:07:47', type:'escalation',msg:'ESCALATE: confidence < τ=0.50 — routing to human reviewer' },
  { time:'19:07:48', type:'action',    msg:'Executor: WRITE approve_loan(case_id=BPI17-4440) [token=d7f2.9a1c]' },
  { time:'19:07:49', type:'retrieval', msg:'CAR: filtered 14→6 by stage=final_review ∩ timestamp validity' },
  { time:'19:07:49', type:'scv',       msg:'SCV: VIOLATION not-coexistence(approve,reject) — cost=2.0 — repair hint: remove reject' },
];

/* ── Main Dashboard ─────────────────────────────────────────── */
export default function Dashboard() {
  const [activeNode, setActiveNode]   = useState(null);
  const [logEntries, setLogEntries]   = useState(MOCK_LOGS.slice(0, 4));
  const [runProgress, setRunProgress] = useState(34);
  const logRef = useRef(null);

  /* Simulate streaming logs */
  useEffect(() => {
    const idx = { current: 4 };
    const timer = setInterval(() => {
      if (idx.current < MOCK_LOGS.length) {
        setLogEntries(prev => [...prev, MOCK_LOGS[idx.current++]]);
      } else {
        idx.current = 0;
        setLogEntries([]);
      }
    }, 2200);
    return () => clearInterval(timer);
  }, []);

  /* Auto-scroll log */
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logEntries]);

  /* Animate progress */
  useEffect(() => {
    const t = setInterval(() => {
      setRunProgress(p => p >= 100 ? 0 : p + 0.4);
    }, 120);
    return () => clearInterval(t);
  }, []);

  const nodeInfo = {
    car:  { title: 'Constraint-Aware Retriever', color: 'cyan',   desc: 'Filters evidence by process state, timestamp validity and reachability. Score = α·sim + β·prox + γ·match.' },
    scv:  { title: 'Symbolic Constraint Verifier', color: 'violet', desc: 'Checks alignment cost, Declare automata, policy predicates and cross-agent conflicts before issuing a plan token.' },
    plan: { title: 'LangGraph Planner', color: 'gold',   desc: 'Produces schema-validated adaptation plans. Must cite evidence provenance IDs. Reports self-assessed confidence.' },
    exec: { title: 'ReAct Executor', color: 'green',  desc: 'Least-privilege MCP tool agent. Write tools only unlock with a valid SCV-signed plan token.' },
  };

  return (
    <div className="page-wrapper">

      {/* ── Orb Hero ── */}
      <div className="orb-hero" style={{ marginBottom: 'var(--space-lg)' }}>
        <div className="orb-hero-left">
          <HoloOrb
            onNodeClick={setActiveNode}
            activeNode={activeNode}
            violationCount={3}
          />
        </div>

        <div className="orb-hero-right">
          <div>
            <div className="holo-subtitle" style={{ marginBottom: 8 }}>
              CONSTRAINT-AWARE MULTI-AGENT WORKFLOW ADAPTATION
            </div>
            <h1 className="holo-title orb-hero-title">
              CARMA
            </h1>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginTop: 12, maxWidth: 500, lineHeight: 1.7 }}>
              Two constraint layers — retrieval-side (CAR) and action-side (SCV) — wrap a
              4-agent LangGraph team running on public BPI event logs across 8 configurations
              and 3 LLMs. Click an orbital node to inspect the component.
            </p>
          </div>

          {/* Node detail panel */}
          {activeNode && nodeInfo[activeNode] && (
            <div className={`glass-card accent-${nodeInfo[activeNode].color}`}
                 style={{ padding: 'var(--space-md)', animation: 'card-appear 0.3s ease both' }}>
              <div className="flex items-center gap-sm mb-md">
                <span className={`badge badge-${nodeInfo[activeNode].color}`}>
                  {activeNode.toUpperCase()}
                </span>
                <span style={{ fontSize: 13, fontWeight: 600 }}>
                  {nodeInfo[activeNode].title}
                </span>
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                {nodeInfo[activeNode].desc}
              </p>
              <button className="btn btn-ghost" style={{ marginTop: 12, fontSize: 10 }}
                      onClick={() => setActiveNode(null)}>
                DISMISS
              </button>
            </div>
          )}

          {/* Status grid */}
          <div className="orb-status-grid">
            {[
              { icon: '🟢', label: 'LangGraph',  value: 'RUNNING',    color: 'var(--holo-green)' },
              { icon: '🔵', label: 'Qdrant',      value: 'INDEXED',    color: 'var(--holo-cyan)' },
              { icon: '🟣', label: 'Declare4Py',  value: 'ACTIVE',     color: 'var(--holo-violet)' },
              { icon: '🟡', label: 'PM4Py',       value: 'REPLAYING',  color: 'var(--holo-gold)' },
            ].map(s => (
              <div key={s.label} className="orb-status-item">
                <span className="orb-status-icon" style={{ background: s.color, boxShadow: `0 0 6px ${s.color}` }} />
                <span style={{ color: 'var(--text-muted)', minWidth: 70 }}>{s.label}</span>
                <span style={{ color: s.color, fontWeight: 600 }}>{s.value}</span>
              </div>
            ))}
          </div>

          <div className="flex gap-sm">
            <a href="/experiments/new" className="btn btn-solid" style={{ textDecoration: 'none' }}>
              <FlaskConical size={13} /> New Experiment
            </a>
            <a href="/benchmark" className="btn btn-primary" style={{ textDecoration: 'none' }}>
              <GitBranch size={13} /> View Benchmark
            </a>
          </div>
        </div>
      </div>

      {/* ── KPI Row ── */}
      <div className="kpi-row" style={{ marginBottom: 'var(--space-lg)' }}>
        <KpiTile label="Total Cases"     value={840}   color="cyan"   icon={Activity}     delta="+120 new" deltaDir="up"   delay={0}   />
        <KpiTile label="Task Success"    value={87}    unit="%" color="green"  icon={CheckCircle}  delta="+2.1% vs B6" deltaDir="up" delay={80}  />
        <KpiTile label="Violation Rate"  value={7}     unit="%" color="rose"   icon={ShieldX}      delta="-15.2% vs B4" deltaDir="down" delay={160} />
        <KpiTile label="Escalations"     value={42}    color="gold"   icon={TriangleAlert} delta="12 pending" deltaDir="up" delay={240} />
        <KpiTile label="Avg Latency"     value={12}    unit="s" color="violet" icon={Clock}         delta="+3.1s vs B6" deltaDir="up" delay={320} />
      </div>

      {/* ── Main grid ── */}
      <div className="dashboard-grid">

        {/* Config comparison */}
        <div className="glass-card col-span-7" style={{ animationDelay: '100ms' }}>
          <div className="flex items-center justify-between mb-lg">
            <div>
              <div className="holo-subtitle" style={{ marginBottom: 4 }}>CONFIGURATION MATRIX</div>
              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>B0–B7 · Constraint Violation Rate vs Task Success Rate</div>
            </div>
            <span className="badge badge-cyan">2×2 Factorial</span>
          </div>

          <div className="config-matrix">
            {/* Header */}
            <div className="config-row" style={{ color: 'var(--text-muted)', fontSize: 10, letterSpacing: '0.1em' }}>
              <span>CODE</span>
              <span>CONFIGURATION</span>
              <span>CAR</span>
              <span>SCV</span>
              <span>CVR↓</span>
              <span>TSR↑</span>
            </div>

            {CONFIGS.map(c => (
              <div key={c.code}
                   className={`config-row ${c.code === 'B7' ? 'highlighted' : ''}`}>
                <div className={`config-badge badge-${c.color}`}
                     style={{ background: `rgba(var(--raw-color,0),0.1)` }}>
                  <span className={`glow-text-${c.color}`}>{c.code}</span>
                </div>
                <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>{c.name}</span>
                <span style={{ fontSize: 11, color: c.car ? 'var(--holo-cyan)' : 'var(--text-muted)' }}>
                  {c.car ? '✓ ON' : '✗ OFF'}
                </span>
                <span style={{ fontSize: 11, color: c.scv ? 'var(--holo-violet)' : 'var(--text-muted)' }}>
                  {c.scv ? '✓ ON' : '✗ OFF'}
                </span>
                <span className={`mono-text`}
                      style={{ color: parseFloat(c.cvr) < 15 ? 'var(--holo-green)' : parseFloat(c.cvr) > 25 ? 'var(--holo-rose)' : 'var(--holo-gold)' }}>
                  {c.cvr}
                </span>
                <span className="mono-text"
                      style={{ color: parseFloat(c.tsr) > 80 ? 'var(--holo-green)' : 'var(--text-secondary)' }}>
                  {c.tsr}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Live experiment feed */}
        <div className="glass-card col-span-5" style={{ animationDelay: '150ms' }}>
          <div className="flex items-center justify-between mb-md">
            <div className="holo-subtitle">LIVE AUDIT STREAM</div>
            <span className="badge badge-green">
              <span style={{ width:5,height:5,borderRadius:'50%',background:'var(--holo-green)',animation:'status-blink 1s infinite',display:'inline-block' }} />
              STREAMING
            </span>
          </div>

          {/* Progress */}
          <div className="metric-bar-wrap" style={{ marginBottom: 'var(--space-md)' }}>
            <div className="metric-bar-label">
              <span>Run progress · B7 · seed=1</span>
              <span className="mono-text">{runProgress.toFixed(0)}%</span>
            </div>
            <div className="metric-bar-track">
              <div className="metric-bar-fill cyan" style={{ width: `${runProgress}%` }} />
            </div>
          </div>

          {/* Log feed */}
          <div className="log-terminal" ref={logRef}>
            {logEntries.map((e, i) => (
              <div key={i} className="log-entry">
                <span className="log-time">{e.time}</span>
                <span className={`log-type ${e.type}`}>[{e.type.toUpperCase().slice(0,5)}]</span>
                <span className="log-msg">{e.msg}</span>
              </div>
            ))}
            <div style={{ display:'flex',gap:4,marginTop:4 }}>
              <span style={{ color:'var(--holo-cyan)',fontFamily:'var(--font-mono)',fontSize:11 }}>›</span>
              <span style={{ width:8,height:14,background:'var(--holo-cyan)',display:'inline-block',
                            animation:'status-blink 0.8s steps(1) infinite',opacity:0.8 }} />
            </div>
          </div>
        </div>

        {/* Research Questions */}
        <div className="glass-card col-span-12" style={{ animationDelay: '200ms' }}>
          <div className="holo-subtitle" style={{ marginBottom: 'var(--space-md)' }}>RESEARCH QUESTIONS</div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:'var(--space-md)' }}>
            {[
              { rq:'RQ1', color:'cyan',   h:'H1', title:'Constraint-Aware Retrieval', metric:'Procedural precision@k · Stage accuracy · Macro-F1', compare:'CAR vs Vector RAG vs GraphRAG' },
              { rq:'RQ2', color:'violet', h:'H2', title:'Pre-Exec Symbolic Verification', metric:'CVR · Violation cost · p95 latency', compare:'B4 vs B6 (SCV on/off)' },
              { rq:'RQ3', color:'gold',   h:'H3', title:'Complementary Mechanisms', metric:'TSR · Conformance fitness · Per-scenario', compare:'B4–B7 factorial interaction' },
              { rq:'RQ4', color:'green',  h:'H4', title:'Scaffolding for Small Models', metric:'Config × model interaction', compare:'8B vs 30B vs Frontier' },
            ].map(r => (
              <div key={r.rq} className={`glass-card rq-card accent-${r.color}`}
                   style={{ padding:'var(--space-md)', margin:0 }}>
                <div className="rq-number" style={{ color:`var(--holo-${r.color})` }}>{r.rq}</div>
                <div className="rq-tag">{r.rq}</div>
                <div style={{ fontSize:13, fontWeight:600, marginBottom:8 }}>{r.title}</div>
                <div style={{ fontSize:11, color:'var(--text-muted)', lineHeight:1.6, marginBottom:8 }}>{r.metric}</div>
                <span className={`badge badge-${r.color}`} style={{ fontSize:9 }}>{r.compare}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Metric bars */}
        <div className="glass-card col-span-4" style={{ animationDelay: '250ms' }}>
          <div className="holo-subtitle" style={{ marginBottom:'var(--space-md)' }}>CARMA (B7) — KEY METRICS</div>
          <div style={{ display:'flex', flexDirection:'column', gap:'var(--space-md)' }}>
            {[
              { label:'Task Success Rate', value:87, color:'green' },
              { label:'Conformance Fitness', value:91, color:'cyan' },
              { label:'Stage Accuracy', value:84, color:'cyan' },
              { label:'Escalation Precision', value:78, color:'gold' },
              { label:'Constraint Violation Rate', value:7, color:'rose', invert:true },
            ].map(m => (
              <div key={m.label} className="metric-bar-wrap">
                <div className="metric-bar-label">
                  <span>{m.label}</span>
                  <span className="mono-text">{m.value}%</span>
                </div>
                <div className="metric-bar-track">
                  <div className={`metric-bar-fill ${m.color}`} style={{ width: `${m.value}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Scenario breakdown */}
        <div className="glass-card col-span-4" style={{ animationDelay: '300ms' }}>
          <div className="holo-subtitle" style={{ marginBottom:'var(--space-md)' }}>SCENARIO BREAKDOWN</div>
          {[
            { code:'S0', name:'Nominal',           cvr: 4, color:'green' },
            { code:'S1', name:'Exception',          cvr:11, color:'cyan' },
            { code:'S2', name:'Rule Change',        cvr: 8, color:'cyan' },
            { code:'S3', name:'Structural Drift',   cvr:12, color:'gold' },
            { code:'S4', name:'Ambiguous Input',    cvr:14, color:'gold' },
            { code:'S5', name:'Conflicting Intents',cvr:18, color:'rose' },
            { code:'S6', name:'Adversarial',        cvr: 9, color:'violet' },
          ].map(s => (
            <div key={s.code} className="flex items-center gap-md" style={{ marginBottom:10 }}>
              <span className={`badge badge-${s.color}`} style={{ width:30, justifyContent:'center' }}>{s.code}</span>
              <span style={{ fontSize:11, color:'var(--text-secondary)', flex:1 }}>{s.name}</span>
              <div style={{ width:80 }}>
                <div className="metric-bar-track">
                  <div className={`metric-bar-fill ${s.color}`} style={{ width:`${s.cvr*4}%` }} />
                </div>
              </div>
              <span className="mono-text" style={{ width:28, textAlign:'right', color:`var(--holo-${s.color})` }}>{s.cvr}%</span>
            </div>
          ))}
        </div>

        {/* Stats summary */}
        <div className="glass-card col-span-4" style={{ animationDelay: '350ms' }}>
          <div className="holo-subtitle" style={{ marginBottom:'var(--space-md)' }}>STATISTICAL TESTS</div>
          <div style={{ display:'flex', flexDirection:'column', gap:'var(--space-sm)' }}>
            {[
              { test:"McNemar (B4→B7)", stat:"χ²=41.3", p:"p<0.001", sig:true,  note:"OR=3.42 [2.1–5.6]" },
              { test:"CAR main effect", stat:"OR=2.1",   p:"p<0.001", sig:true,  note:"Holm-corrected" },
              { test:"SCV main effect", stat:"OR=2.8",   p:"p<0.001", sig:true,  note:"Holm-corrected" },
              { test:"CAR×SCV interaction",stat:"β=0.4", p:"p=0.031", sig:true,  note:"Mixed logistic" },
              { test:"Friedman (latency)",  stat:"χ²=6.1",p:"p=0.19",  sig:false, note:"Cliff's δ=0.18" },
              { test:"Model×Config (RQ4)", stat:"β=−0.7",p:"p=0.007", sig:true,  note:"8B scaffolded most" },
            ].map(t => (
              <div key={t.test} className="flex items-center gap-sm"
                   style={{ padding:'6px 8px', borderRadius:'var(--radius-sm)',
                            background:'rgba(0,0,0,0.2)', border:'1px solid var(--border-dim)' }}>
                <span style={{ flex:1, fontSize:11, color:'var(--text-secondary)' }}>{t.test}</span>
                <span className="mono-text" style={{ fontSize:10, color:'var(--text-muted)' }}>{t.stat}</span>
                <span className={`badge ${t.sig ? 'badge-green' : 'badge-violet'}`} style={{ fontSize:9 }}>{t.p}</span>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
