# CARMA — OSF Preregistration form (template "OSF Preregistration", v4)

The text of each field as it is submitted, in the template's order. A heading
`## <key> · <field>` holds the answer to that field; the full protocol is
`docs/OSF_PREREGISTRATION.md`, attached to the registration.

**Title.** Constraint-Aware Retrieval and Verification for Multi-Agent Workflow Adaptation: a controlled factorial study on WF-Adapt

**Description.** A preregistered factorial experiment on whether constraint-aware retrieval (CAR) and a symbolic constraint verifier (SCV) make LLM agent teams adapt business-process cases with fewer constraint violations and more task success, on 196 benchmark cases built from four public event logs, with two open-weight models of one family (gpt-oss-20b, gpt-oss-120b).

---

## 344-2 · Research questions or hypotheses

RQ1 (retrieval side): does constraint-aware retrieval (CAR) reduce constraint violations and improve task success compared with plain vector retrieval?
RQ2 (action side): does a symbolic constraint verifier (SCV) that gates execution reduce constraint violations?
RQ3 (interaction): do CAR and SCV interact?
RQ4 (model size): does the reliability gain depend on the size of the model?

H1. CAR lowers the constraint-violation rate relative to vector retrieval in an agent team (B5 vs B4). Secondary to H1: CAR yields higher procedural precision@k and stage accuracy of the evidence pack (B5 vs B4).
H2. The SCV lowers the constraint-violation rate relative to an unconstrained team (B6 vs B4).
H3. CAR and SCV interact positively, and full CARMA (B7) has the lowest violation rate among the LLM configurations (B7 vs B4, B5 and B6).
H4. The reliability gain of CARMA over the unconstrained team (B7 vs B4) is larger for the smaller model.

Exploratory, not tested confirmatorily: the rule-based baseline B0 is best on unperturbed cases (S0) and fails under rule change (S2) and structural drift (S3); B0's outcomes were observed before registration.

## 344-4 · Foreknowledge of data or evidence

Authors have observed the data, but have not performed the proposed analyses. At least some of the data that will be used for this analysis plan has been accessed and observed by the authors. The authors have sufficiently observed relevant evidence to influence their analysis decisions or conclusions. However, the authors have not yet performed any of the proposed analyses in this plan and will not do so until after this plan is registered.

## 344-14 · Explanation of foreknowledge and managing unintended influences

Observed before registration:
1. The four public event logs (BPI Challenge 2017, BPI Challenge 2020 travel permits, Road Traffic Fine Management, Helpdesk) and the benchmark built from them — cases and automated references — while developing and validating the benchmark builder.
2. Outcomes of the rule-based baseline B0 (deterministic, no language model) on all evaluation cases: overall task success 0.296, violation rate 0.067, observed while validating the scoring rules. Because of this, all B0 contrasts are exploratory.
3. Retired pilot runs of B4 and B7 with gpt-4o (a model not in this study) on 28 evaluation cases. They revealed a contradictory planner rule and a missing goal definition, which were fixed before registration. These 28 cases are excluded from the study (moved to a split that is never evaluated; ids in artifacts/preregistration/seen_cases.json).
4. B7 runs of both registered models on the separate pilot split (84 cases, disjoint from the evaluation split): tuning of the escalation threshold τ and a measurement of tokens per case on 2 pilot cases.

No output of a registered model (gpt-oss-20b, gpt-oss-120b) on an evaluation case exists. The software refuses to run any LLM configuration on the evaluation split until this registration's URL is recorded in its settings, and stores the URL with every run. The primary outcomes are scored by a deterministic program, not by people.

## 344-17 · Study type

Simulation study: Using existing or synthetic data to assess performance of a model, mimic operation of an existing or proposed system, or predict possible outcomes in a controlled context. This may include demonstration of methods, many varieties of modeling, prediction of policy impacts, simulating behavior or outcomes in a population, and other designs.

## 344-27 · Intention for causal interpretation

Direct inference on causal relationship(s): This study is intended to infer or estimate a causal relationship between two or more variables. It is designed specifically for the purposes of causal inference or identification.

## 344-32 · Blinding of experimental treatments

Subjects will not be aware of the assigned treatment during data collection (either because the subjects are not human participants or because of blinding procedures).

## 344-38 · Additional blinding during research or analysis

The subjects are benchmark cases processed by software agents. All primary and secondary outcomes are computed by a deterministic scorer from the executed trace, the constraint set and the reference; no human judgment enters them. The reference audit (see Data collection procedures) shows the case and its reference only, never a configuration's output.

## 344-40 · Study design

Controlled within-case factorial experiment. Every configuration runs on the same benchmark cases; the case is the unit of pairing.

Configurations: B0 rule-based baseline (no model, no retrieval). B1 single LLM agent, no retrieval. B2 single agent + vector retrieval. B3 single agent + graph retrieval. B4 four-agent team (coordinator, planner, critic, executor) + vector retrieval. B5 team + constraint-aware retrieval (CAR). B6 team + vector retrieval + symbolic constraint verifier (SCV). B7 full CARMA: team + CAR + SCV + escalation gate.

B4–B7 form the 2 × 2 factorial {CAR off/on} × {SCV off/on}; this factorial is the confirmatory part. In B6 and B7 a plan the verifier rejects returns to the planner with the verifier's report, at most k = 3 times; a plan still rejected does not run (B6) or is handed to a human (B7). B7 also escalates when the plan's confidence is below the tuned threshold τ or the team flags a conflict. The verifier scores every configuration's plan so that violation rates are comparable; scoring never changes what runs.

Two models of one family, gpt-oss-20b (small) and gpt-oss-120b (large), served by Groq's free tier, temperature 0.2, seed 42, reasoning effort "low" for every configuration. Prompts are identical across configurations. The configurations of a model run case-major (every configuration runs a case before the next case starts), so that a change of the hosted model during the weeks of the study affects all configurations alike.

## 344-44 · Randomization

No random assignment: every configuration runs on every case (within-case design). Case selection is seeded and blind to outcomes (see Data collection procedures). Model sampling uses temperature 0.2 with seed 42; seeds 43 and 44 are exploratory.

## 344-47 · Data collection procedures

Event logs (public): BPI Challenge 2017, doi:10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b; BPI Challenge 2020 travel permits, doi:10.4121/uuid:52fb97d4-4588-43c9-9d04-3604d4613b51; Road Traffic Fine Management, doi:10.4121/uuid:270fd440-1057-4fb9-89a9-b699b47990f5; Helpdesk, doi:10.17632/39bp3vv62t.1.

Each log is split 70 % training / 30 % test by case start time. The process model (Inductive Miner), the Declare and policy constraints and the knowledge corpus are built from the training split only; benchmark cases come from the test split only.

Scenarios: S0 nominal, S1 exception (missing document), S2 rule change (a rule version in force or not yet in force), S3 structural drift (renamed activity), S4 ambiguous request, S5 conflicting intents, S6 adversarial instruction. For every log and scenario, 30 evaluation cases are drawn by a seeded shuffle (seed 42) from the test split; a case is used only if its observed continuation complies with the mined constraints (the observed continuation is the reference of S0, S3, S5 and S6), and the next case in the seeded order replaces a skipped one. A pilot split of 3 further cases per log and scenario (84 cases) is used only for tuning. Each case receives an automated reference: a strategy and an activity sequence; a reference may break the constraints only in S1, where the cheapest non-compliant path is right when no compliant one exists. The builder rejects any other non-compliant reference.

Reference audit: before analysis, the first author checks the references of a random 20 % of the confirmatory cases (stratified by scenario, seed 42) on the platform's Annotate page, which shows the case and its reference but no configuration output. The share of rejected references is reported; a rejected reference's case is excluded from every configuration.

Runs: each configuration × model runs on the confirmatory sample; every case's plan, executed trace, verifier report, retrieved documents, tokens, latency and the served model version are stored with a hash-chained audit log. A model call that fails is retried (rate limits are waited out); when the model cannot be reached the run pauses and later resumes at its first case without an outcome.

## 344-51 · Sample size

196 evaluation cases — 7 per log × scenario cell (28 per scenario, 49 per log), the first 7 of each cell in case-id order (random UUIDs) among the 807 cases of the evaluation split. Each of B1–B7 runs on all 196 cases with each of the 2 models (2 744 adaptations). B0 runs on all 807 cases; its comparisons use the 196 shared cases.

## 344-53 · Sample size rationale

Power for the confirmatory McNemar tests: detecting a 10-point difference in violation rate with about 15 % discordant pairs at power 0.80 requires 197 paired cases at the strictest Holm step (α = 0.05/10, two-sided, normal approximation); 196 cases reach power 0.80 there and more at every later Holm step. The free tier's daily token quota (200 000 tokens per model; about 15 000 tokens per case for B4–B7) bounds the study at about two to five weeks per model, which rules out the full evaluation split. Per-scenario estimates (28 cases each) are descriptive.

## 344-55 · Starting and stopping rules

Runs on the evaluation split start only after this registration exists. Every registered configuration × model runs on all 196 confirmatory cases with seed 42; no run is stopped, repeated or extended on the basis of its results. Cases are independent, so a run interrupted for technical reasons (model unreachable, machine restarted) resumes at its first case without an outcome; a case whose model could not be reached is not scored but run again.

## 344-58 · Manipulated variables

Configuration (B0–B7), defined by four components: retrieval (none / vector / graph / constraint-aware), agents (single agent / four-agent team), symbolic constraint verifier acting on the plan (off / on), escalation gate (off / on). The confirmatory factorial is CAR (B4, B6: vector; B5, B7: constraint-aware) × SCV (B4, B5: off; B6, B7: on).
Model: gpt-oss-20b vs gpt-oss-120b.
Scenario (S0–S6) is a property of the case, balanced in the sample (28 cases each).

## 344-62 · Measured variables

Per case and configuration:
- Constraint violation (primary): the executed trace violates at least one hard constraint. A blocked, declined or escalated plan executes nothing.
- Task success (primary): the goal is reached with no hard violation. Goal: the executed continuation ends with an end activity of the process (those its training traces end with) or with the reference's last activity; for the strategies that leave the case to a human (escalate for approval, request clarification, escalate the conflict) the goal is reached when the system escalated or the agent declined.
- Adaptation correctness: exact match of the executed sequence with the reference sequence; 2·LCS similarity.
- Unsafe action: a hard-violating write action was executed.
- Escalation: the case was handed to a human.
- Retrieval (configurations with retrieval): procedural precision@k and stage accuracy of the evidence pack (definitions under Indices).
- Efficiency: latency, tokens, number of model calls.

## 344-66 · Indices

Violation rate (CVR) and task success rate (TSR): share of cases with the outcome, per configuration × model.
Similarity: 2·LCS(executed, reference) / (|executed| + |reference|); partial match = similarity ≥ 0.5.
Procedural precision@k: of the k documents in the evidence pack, the share that refer to an activity enabled in the case's current state or required by its scenario frame and are not marked superseded or not yet in force for the case.
Stage accuracy: of the k documents, the share whose stage equals the case's current stage (deterministic state estimate from the executed prefix).
Effect size for paired binary outcomes: conditional odds ratio of the discordant pairs, with the Haldane–Anscombe correction (0.5 added to each discordant cell) when a cell is empty.

## 344-71 · Statistical models

Confirmatory, per model: exact McNemar tests on paired cases for violation and for task success on five contrasts — B5–B4 (H1), B6–B4 (H2), B7–B4, B7–B5 and B7–B6 (H3) — 10 tests per model.
Factorial effects: mixed-effects logistic regression of violation (and of task success) on CAR, SCV and CAR × SCV (B4–B7), model and scenario as fixed effects, with random intercepts for case and process. The CAR × SCV term tests the interaction of H3; for H4 the same model on B4 and B7 with a configuration × model term.
Secondary to H1: Wilcoxon signed-rank tests of procedural precision@k and stage accuracy, B5 vs B4, Holm-corrected between the two.
Continuous outcomes (latency, tokens): Friedman test across configurations, Wilcoxon signed-rank post-hoc tests with Holm correction, Cliff's δ, 10 000-resample bootstrap 95 % confidence intervals.

## 344-75 · Transformations

Outcomes are coded 0/1 per case. A case whose model output could not be used (no parseable plan after the retries) counts as not successful and as not violating, since nothing is executed; failures are reported per configuration. No other transformation.

## 344-77 · Inference criteria

α = 0.05, two-sided. The 10 confirmatory McNemar tests of a model are Holm-corrected together. A hypothesis is supported when its contrast is significant after correction in the predicted direction (fewer violations for H1–H3). H3's interaction and H4: the corresponding mixed-model term at p < 0.05 in the predicted direction. All other comparisons (B0–B3, per scenario, seeds 43–44) are exploratory and Holm-corrected among themselves.

## 344-79 · Data inclusion and exclusion

Included: the 196 confirmatory cases of the evaluation split. Excluded before any run: the 5 cases whose activities the discovered model does not contain, the 28 cases on which a model was run before registration, the 84 pilot cases, and any case whose reference the audit rejects. No case is excluded on the basis of a configuration's output.

## 344-81 · Missing data

A case interrupted by an outage is run again, not scored. A model failure that persists after the retries is recorded as a failed case and counts as not successful. Should a case have no outcome for some configuration at the end of the study, it is left out of the contrasts that involve that configuration, and the number of such cases is reported.

## 344-83 · Other planned analysis

Exploratory: B0 per-scenario contrasts; the single-agent configurations B1–B3 against the team; per-scenario and per-log breakdowns; escalation, unsafe-action and correctness rates; seeds 43 and 44 on B4 and B7 for run-to-run variation; cost in tokens and latency.

## 344-86 · Context and additional information

Deviations from the original proposal, each fixed before any evaluation run: the BPI Challenge 2019 log was replaced by the Helpdesk log (the 2019 log was unavailable from its repository and exceeds the available memory); open-weight models on a free tier replace a paid API model (no budget); references are automated and audited rather than agreed by two annotators; only τ is tuned (α = 0.6, β = 0.2, γ = 0.2, k = 3, top-k = 10 fixed); one confirmatory seed and a 196-case sample instead of three seeds on all cases (free-tier quota); reasoning effort "low" (hidden reasoning tripled the tokens per case). The full protocol, its justification and the list of excluded cases are attached.
