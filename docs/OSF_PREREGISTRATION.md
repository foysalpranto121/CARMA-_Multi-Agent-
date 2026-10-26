# CARMA — OSF Preregistration (draft)

**Title.** Constraint-Aware Retrieval and Verification for Multi-Agent Workflow Adaptation: a controlled factorial study on WF-Adapt
**Authors.** [names, affiliations]
**Date of registration.** [date] — submitted before any evaluation-split run.

Fields marked **[confirm]** need the authors' decision before submission.

---

## 1. Research questions and hypotheses

- **RQ1 — retrieval side.** Does constraint-aware retrieval (CAR) reduce constraint violations and improve task success compared with plain vector retrieval?
- **RQ2 — action side.** Does a symbolic constraint verifier (SCV) that gates execution reduce constraint violations?
- **RQ3 — interaction.** Do CAR and SCV interact?
- **RQ4 — model size.** Does the reliability gain depend on the size of the model?

| | Hypothesis | Test |
|---|---|---|
| **H1** | CAR yields higher procedural precision@k and stage accuracy, and fewer downstream violations, than vector retrieval (B5 vs B4). | McNemar on violations; mixed-effects main effect of CAR |
| **H2** | The SCV lowers the constraint-violation rate relative to an unconstrained team (B6 vs B4). The confidence gate keeps its latency overhead bounded. | McNemar on violations; Friedman/Wilcoxon on latency |
| **H3** | CAR and SCV interact positively; full CARMA (B7) has the lowest violation rate among the LLM configurations. The rule-based baseline B0 is best on unperturbed cases (S0) and fails under rule change (S2) and drift (S3). | CAR × SCV term of the mixed model; per-scenario contrasts |
| **H4** | The reliability gain of CARMA over the unconstrained team (B7 vs B4) is larger for the smaller model. | configuration × model term of the mixed model |

## 2. Design

A controlled repeated-measures experiment. Every configuration runs on the same benchmark cases; cases are the unit of pairing.

| Code | Configuration | Retrieval | Agents | Verifier acts | Escalation gate |
|---|---|---|---|---|---|
| B0 | Rule-based baseline | — | — (deterministic) | — | — |
| B1 | Single LLM | — | 1 | — | — |
| B2 | Single LLM + vector RAG | vector | 1 | — | — |
| B3 | Single LLM + GraphRAG | graph | 1 | — | — |
| B4 | Team + vector RAG | vector | 4 | — | — |
| B5 | Team + CAR | constraint-aware | 4 | — | — |
| B6 | Team + vector RAG + SCV | vector | 4 | yes | — |
| B7 | CARMA full | constraint-aware | 4 | yes | yes |

B4–B7 form the 2 × 2 factorial {CAR, SCV}. In B6/B7 a plan the verifier rejects returns to the planner with the violation report, at most *k* times; a plan still rejected does not run (B6) or is escalated (B7). The verifier also *scores* every configuration's plan so that violation rates are comparable; scoring never changes what runs.

**Models.** Two open-weight models of one family, run on the Groq free tier: **gpt-oss-20b** (small) and **gpt-oss-120b** (large) — the same training recipe at two sizes isolates the size contrast of H4. The served model version is recorded per call. **[confirm]** a frontier API model (e.g. `gpt-4o`) is added if funding allows.
**Sampling.** Temperature 0.2; seeds 42, 43, 44.
**Prompts.** Identical across configurations; a configuration differs only in its components.

## 3. Data — the WF-Adapt benchmark

**Event logs.** Four public logs, each split 70 % training / 30 % test by case start time:

| Key | Log | Domain |
|---|---|---|
| bpi2017 | BPI Challenge 2017 (doi:10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b) | loan origination |
| bpi2020 | BPI Challenge 2020, travel permits (doi:10.4121/uuid:52fb97d4-4588-43c9-9d04-3604d4613b51) | travel expenses |
| rtfm | Road Traffic Fine Management (doi:10.4121/uuid:270fd440-1057-4fb9-89a9-b699b47990f5) | public administration |
| helpdesk | Helpdesk, Polato 2017 (doi:10.17632/39bp3vv62t.1) | IT service management |

The process model (Inductive Miner), the Declare and policy constraints and the knowledge corpus are built from the **training** split only; benchmark cases come from the **test** split only.

**Scenarios.** S0 nominal · S1 exception (missing document) · S2 rule change (version in force or not yet in force) · S3 structural drift (renamed activity) · S4 ambiguous request · S5 conflicting intents · S6 adversarial instruction.

**Case selection.** Per log and scenario, 30 evaluation cases are drawn by a seeded shuffle (seed 42) from the test split. A case is used only if its observed continuation complies with the mined frame, because the observed continuation is the reference of S0, S3, S5 and S6 and an unreachable reference could not be scored. The next case in the seeded order replaces a skipped one. Each case receives an automated reference (strategy and activity sequence); a reference may break the frame only in S1, where the cheapest non-compliant path is the right answer when no compliant one exists.

**Size.** 840 evaluation cases built, **835 validated** (5 Helpdesk cases use activities the discovered model does not contain), ≥ 118 per scenario type (the power target is 115; Section 6). A separate **pilot split** of 84 cases (3 per log and scenario, the next ones in the same seeded order) is used only for tuning (Section 5) and never evaluated.

**References.** **[confirm]** Two annotators check the automated reference of every evaluation case independently on the platform's Annotate page; Cohen's κ over their strategy labels is reported, and cases on which both reject the reference are excluded before the main runs.

## 4. Variables

| Outcome | Definition |
|---|---|
| Constraint-violation rate (CVR) — **primary** | share of cases whose **executed** trace violates at least one hard constraint; a blocked, declined or escalated plan executes nothing |
| Task success rate (TSR) — **primary** | the goal is reached with no hard violation. Goal: the executed continuation ends with an end activity of the process (those its training traces end with) or with the reference's last activity; for the strategies that leave the case to a human (escalate for approval, request clarification, escalate the conflict) the goal is reached when the system escalated or the agent declined |
| Adaptation correctness | exact match with the reference sequence; 2·LCS similarity (partial match ≥ 0.5) |
| Unsafe-action rate | a hard-violating write action executed |
| Escalation rate | share of cases handed to a human |
| Retrieval | procedural precision@k and stage accuracy of the evidence pack |
| Efficiency | p50/p95 latency, tokens, LLM calls, list-price cost |

A case whose model call fails after the retries is recorded as failed and counts as not successful; failures are reported per configuration.

## 5. Tuning (pilot split only)

- **Tuned:** the escalation threshold τ of B7 only. B7 runs once on the pilot split with the confidence gate off; every τ ∈ {0.0, 0.1, …, 0.9} is replayed offline (a plan whose confidence is below τ would have been escalated); the τ with the highest pilot TSR is chosen, ties going to the smaller τ. The chosen value and the full grid are recorded in `artifacts/tuning/tau_<model>.json` and fixed before the main runs. τ is tuned separately for each model, because each model's confidences are calibrated differently.
- **Fixed at their defaults:** α = 0.6, β = 0.2, γ = 0.2 (CAR score weights), k = 3 repair rounds, top-k = 10.

## 6. Analysis plan

- **Pairwise contrasts** on binary outcomes (violation, success): exact McNemar tests on cases paired across configurations; Holm correction across all pairs; effect size = conditional odds ratio, with the Haldane–Anscombe correction (0.5 added to each discordant cell) when a cell is empty. α = 0.05.
- **Factorial effects:** mixed-effects logistic regression with configuration (CAR, SCV and CAR × SCV for B4–B7), model and scenario as fixed effects and random intercepts for case and process. The CAR × SCV term tests H3; configuration × model tests H4.
- **Continuous outcomes** (latency, cost, fitness): Friedman test, Wilcoxon signed-rank post-hoc tests with Holm correction, Cliff's δ, 10,000-resample bootstrap 95 % CIs.
- **Power.** Detecting a 10-point difference in violation rate (α = 0.05, power 0.8, ≈ 15 % discordant pairs) requires ≈ 115 paired cases per scenario type.
- **Stopping rule.** Every registered configuration × model × seed runs on all validated evaluation cases; no run is stopped or repeated on the basis of its results. A run interrupted for technical reasons is restarted from scratch.

## 7. Deviations from the original proposal

| Proposal | This registration | Reason |
|---|---|---|
| BPI Challenge 2019 (purchase-to-pay) | Helpdesk (IT service) | the BPI 2019 log (≈ 700 MB) was unavailable from its repository and exceeds the available memory; Helpdesk is public, light and adds a domain |
| frontier API model + open-weight ≈ 30B + ≈ 8B | gpt-oss-120b + gpt-oss-20b (open-weight, free tier) | no budget for API models; one model family at two sizes keeps the small-vs-large contrast of H4 |
| references = gold adaptations agreed by two annotators | automated references, checked by two annotators **[confirm]** | the reference behaviour is derived from the observed continuation and the scenario rules |
| repair hints from a planner (Fast Downward) | the verifier's violation report is the repair feedback | the planner integration is not part of the artifact |
| executor agent | deterministic executor that runs the approved plan | execution is replayed against the benchmark; the executor cannot change an approved plan |
| tune τ, α, β, γ and k on the pilot split | tune τ only | budget; the pilot showed τ to be the setting that matters |

## 8. Artifact

Code, benchmark export and analysis scripts: [repository URL]. Every run records its configuration, seed, the served model version, the verifier report and a hash-chained audit log.
