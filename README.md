# CARMA — Constraint-Aware Multi-Agent Workflow Adaptation

A research platform for measuring how **retrieval-side** and **action-side** constraint
layers change the reliability of LLM-driven workflow adaptation.

The platform implements the factorial design of the accompanying research proposal:
8 configurations (**B0–B7**) × 3 LLM back-ends × 3 seeds, replayed over an annotated
workflow-adaptation benchmark built from public BPI event logs.

---

## Architecture

```
carma-backend/                Django 5.1 · DRF · Channels · Celery
├── carma_engine/             The research engine (framework-independent)
│   ├── constraint_knowledge/ Constraint-graph compiler
│   ├── state_estimator/      Prefix-trace replay → process state
│   ├── retriever/            Dense, graph and constraint-aware retrieval
│   ├── agents/               Coordinator → Planner → Critic → Executor (+ policy auditor)
│   ├── verifier/             Symbolic Constraint Verifier (SCV) + conflict detection
│   ├── escalation/           Confidence-gated human escalation
│   └── runners/              B0–B7 runners (the experimental conditions)
├── apps/
│   ├── users/                Custom user model, JWT, role-based permissions
│   ├── processes/            Process frames, constraint sets, retrieval corpus
│   ├── benchmark/            Event logs, cases, S0–S6 scenarios, XES import
│   ├── experiments/          Run orchestration, adaptations, run results
│   ├── metrics/              Real statistical analysis (McNemar, Friedman, Wilcoxon, Holm, bootstrap)
│   ├── reviews/              Escalation queue and human review decisions
│   └── audit/                Append-only SHA-256 hash chain with replay
└── config/                   Settings, URLs, Celery, ASGI, platform status

carma-frontend/               React 18 · Vite · TanStack Query · Zustand
└── src/
    ├── api/                  Typed API client for the whole backend surface
    ├── components/           App shell, auth guard, shared UI primitives
    ├── pages/                Dashboard, Processes, Benchmark, Experiments, Metrics, Review, Audit
    └── store/                Persisted auth store with server-backed role hierarchy
```

### The two constraint layers

| Layer | Where | What it does |
|---|---|---|
| **CAR** — Constraint-Aware Retrieval | `carma_engine/retriever/` | Filters and scores evidence by process state, timestamp validity and graph reachability. Score = `α·sim + β·prox + γ·match`. |
| **SCV** — Symbolic Constraint Verifier | `carma_engine/verifier/` | Checks alignment cost, Declare-style automata, policy predicates and cross-agent conflicts *before* any write action, and issues a signed plan token. |

### What the state estimator reports

`carma_engine/state_estimator/replay.py` replays the executed prefix on the
discovered model and reports four things:

| Field | Meaning |
|---|---|
| `stage` | the activity the case is currently in |
| `enabled_activities` | the activities the model allows next (the model's *silent* structural steps are traversed, but only one step deep — a deeper search returns the whole process, not a state) |
| `required_activities` | the obligations the prefix left open: the responses, successions and existences the frame still requires of the continuation |
| `forbidden_activities` | the activities the frame rules out for the continuation (absence, not-coexistence, exhausted exact-counts) |

`required_activities` and `forbidden_activities` are what a declarative frame
contributes to the agent: the state is not only a control-flow position, it is
a control-flow position *plus the set of obligations that are still due*.
The rule-based runner (B0) discharges them mechanically; the LLM runners
receive them in the planner prompt and must put them into the plan.

### The experimental matrix

| Code | Configuration | CAR | SCV | Agents |
|------|---------------|-----|-----|--------|
| B0 | Rule-based baseline | – | – | 0 |
| B1 | Single LLM | – | – | 1 |
| B2 | Single LLM + VectorRAG | – | – | 1 |
| B3 | Single LLM + GraphRAG | – | – | 1 |
| B4 | Multi-agent + VectorRAG | – | – | 4 |
| B5 | Multi-agent + CAR | ✓ | – | 4 |
| B6 | Multi-agent + SCV | – | ✓ | 4 |
| B7 | **CARMA full** | ✓ | ✓ | 4 |

B4–B7 form the 2×2 factorial over {CAR, SCV} that answers RQ1–RQ3.

---

## Running it

### Backend

```powershell
cd carma-backend
.\setup.ps1                      # venv, dependencies, migrations, seeds, admin account
```

Or manually:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env

$env:DJANGO_SETTINGS_MODULE = "config.settings_sqlite"   # quick start, no services needed
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py seed_configurations     # creates B0–B7
.\venv\Scripts\python.exe manage.py createsuperuser
.\venv\Scripts\python.exe manage.py runserver
```

Two settings modules are available:

| Module | Database | Broker | Use for |
|---|---|---|---|
| `config.settings` | PostgreSQL | Redis | The actual research study |
| `config.settings_sqlite` | SQLite file | in-process (Celery eager) | Development, demos, CI |

`config.settings_test` (in-memory SQLite) is what the test-suite uses.

### Frontend

```powershell
cd carma-frontend
npm install
npm run dev        # http://localhost:5173
```

Vite proxies `/api`, `/health` and `/ws` to `http://localhost:8000`.

### Verification

```powershell
cd carma-backend
.\venv\Scripts\python.exe -m pytest      # 47 tests
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py makemigrations --check
```

```powershell
cd carma-frontend
npm run build
```

---

## The WF-Adapt benchmark

`WF-Adapt` is built from four public event logs, mined once into a frame and
annotated with seven perturbation scenarios:

| Dataset | Source | What it contributes |
|---|---|---|
| `bpi2017` | BPI Challenge 2017 — Loan Application | loan origination with a long, branching trace |
| `bpi2019` | BPI Challenge 2019 — Purchase-to-Pay | invoice handling with many trace variants |
| `bpi2020` | BPI Challenge 2020 — Travel Permit | a small, shallow process |
| `rtfm` | Road Traffic Fine Management | a public-administration process with high variance |

Each log is split **70 % training / 30 % test** by case id. The model, the
mined frame and the knowledge corpus are built from the *training* split
only; the benchmark cases are drawn from the *test* split, so no agent ever
sees a test case.

For every log the benchmark contains seven scenarios × 30 cases = 210 cases,
so the full benchmark is **4 × 210 = 840 cases**:

| Scenario | Perturbation | What the case tests |
|---|---|---|
| `S0` | nominal continuation | does the agent continue the case at all? |
| `S1` | compliant exception | does it respect a rule that forbids the obvious step? |
| `S2` | timestamp-valid rule change | does it apply the rule version that is in force at the case timestamp? |
| `S3` | structural rename | does it notice that an activity was renamed? |
| `S4` | ambiguous input | does it ask instead of guessing? |
| `S5` | conflicting intents | does it resolve the conflict by authority, or escalate? |
| `S6` | adversarial content | does it ignore instructions embedded in the data? |

---

## Running the study

### 1 · Fetch the event logs

```powershell
.\scripts\fetch_event_logs.ps1 -DataDir .\carma-backend\data
```

### 2 · Build the benchmark

```powershell
cd carma-backend
.\venv\Scripts\python.exe manage.py import_benchmark `
    --datasets bpi2017 bpi2019 bpi2020 rtfm --cases-per-scenario 30 --seed 42
```

This discovers the control-flow model, mines the Declare and policy
constraints, builds the knowledge corpus (SOPs, rule cards, precedents) and
materialises the 840 benchmark cases.

### 3 · Run the configurations

```powershell
# one configuration, all cases
.\venv\Scripts\python.exe manage.py run_experiment --configs B7 --seed 42

# the whole matrix
.\venv\Scripts\python.exe manage.py run_experiment `
    --configs B0 B1 B2 B3 B4 B5 B6 B7 --seed 42

# pipeline validation without a model endpoint
.\venv\Scripts\python.exe manage.py run_experiment --configs B1 --mock-llm --limit 50
```

### 4 · Analyse and export

```powershell
.\venv\Scripts\python.exe manage.py analyse_experiment --output ../artifacts/wf-adapt/statistics
.\venv\Scripts\python.exe manage.py export_artifacts --output ../artifacts/wf-adapt
```

`run_experiment` is the single-process twin of the Celery task in
`apps/experiments/tasks.py`; both write the same `Adaptation` rows and both
aggregate through the same function, so the numbers are identical.

---


## API surface

| Area | Endpoints |
|---|---|
| Auth | `POST /api/v1/auth/token/`, `POST /api/v1/auth/token/refresh/`, `POST /api/v1/auth/token/blacklist/`, `GET /api/v1/users/me/` |
| Processes | `/api/v1/processes/`, `/api/v1/constraint-sets/`, `/api/v1/constraints/`, `/api/v1/corpus/` |
| Benchmark | `/api/v1/benchmark/scenarios/`, `/api/v1/benchmark/cases/`, `/api/v1/benchmark/cases/stats/`, `POST /api/v1/benchmark/import-log/` |
| Experiments | `/api/v1/experiments/`, `/api/v1/experiments/matrix/`, `POST /api/v1/experiments/{id}/start/`, `/pause/`, `/export/`, `/api/v1/run-configs/`, `/api/v1/adaptations/`, `/api/v1/run-results/` |
| Metrics | `/api/v1/metrics/`, `/api/v1/metrics/statistical-tests/`, `/api/v1/metrics/cost-breakdown/`, `/api/v1/metrics/scenario-breakdown/` |
| Review | `/api/v1/escalations/`, `POST /api/v1/escalations/{id}/assign/`, `/api/v1/reviews/` |
| Audit | `/api/v1/audit/`, `/api/v1/audit/verify-chain/`, `/api/v1/audit/replay/{adaptation_id}/` |
| Platform | `/api/v1/system/status/`, `/health/` |

Interactive schema: `http://localhost:8000/api/docs/`

---

## Roles

| Role | May do |
|---|---|
| `admin` | Everything, including user management. Admins pass every role check. |
| `researcher` | Create processes, run the experiment matrix, read metrics and the audit log. |
| `reviewer` | Work the escalation queue and record human review decisions. |
| `annotator` | Annotate benchmark cases and gold adaptations. |

Public self-registration cannot create an `admin` account — the API rejects it.

---

## Research-integrity rules enforced in code

1. **No fabricated numbers.** Every figure in the UI comes from the API. Statistics are
   computed from recorded adaptations with SciPy; when the data does not support a test,
   the API returns an explicit error instead of a number.
2. **The audit log is append-only.** Each entry stores the SHA-256 hash of its
   predecessor, the sequence number is unique, and updates or deletes raise. The chain is
   verifiable at `/api/v1/audit/verify-chain/`.
3. **Reproducibility.** A run is determined by `(configuration, seed, model version)`.
   LLM sampling parameters live on the configuration record.
4. **Escalation is mandatory, not optional.** When the planner's confidence is below τ or
   the SCV rejects a plan, the adaptation is escalated to a human instead of being
   silently executed.

---

## Known constraints

* The heavy optional dependencies (Qdrant, sentence-transformers, LangGraph, PM4Py) are
  imported lazily. Without them the engine falls back to deterministic, hash-based
  retrieval and a rule-based agent pipeline, so the platform still runs end-to-end.
* Without a reachable LLM provider the LLM-backed runners (B1–B7) degrade to the
  rule-based planner and record the failure in the adaptation's audit trail. The
  configuration matrix still runs; it just does not measure the LLM.
* The full study (840 cases × 8 configurations × 3 models × 3 seeds) is a multi-day
  compute job. Validate the pipeline first with a small slice, e.g. B4 vs B7,
  one model, one seed, 30 cases.
* `statsmodels` (mixed-effects models) and `declare4py` (reference automata checker) are
  not required to run the platform — install them with
  `pip install -r requirements-optional.txt` when the corresponding analysis needs them.
