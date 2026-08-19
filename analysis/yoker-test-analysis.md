# yoker-test: Analysis & Design Document

> **Status**: Brainstorming / Pre-implementation
> **Date**: 2025-01-15
> **Depends on**: `yoker` (as SDK, `>=0.10.1`)

## 1. Vision

**yoker-test** is a standalone Python package that provides a testing
framework for evaluating LLM models running through Yoker. It answers two
complementary questions:

1. **How well does a model run in Yoker?** — Model quality (correctness,
   reasoning, instruction following) measured through Yoker's actual
   backend pipeline.
2. **How well does Yoker run a model?** — By comparing scores across
   Yoker versions with the same model and suite, score changes become an
   indirect regression test for Yoker itself.

The output is a multi-dimensional model profile — not just "how smart is
this model?" but "how efficient is it?", "what does it cost?", and "did
Yoker's changes affect its performance?" — compiled into a landscape
overview of models and how they perform in Yoker.

### 1.1 Positioning

yoker-test is **not** another LLM benchmark framework. It does not aim to
compete with lm-evaluation-harness, lighteval, or Inspect AI. It is
purpose-built for the Yoker ecosystem:

- Tests run **through Yoker's actual backend layer** (`process()`,
  `Agent.process()`, or `backend.chat_stream()`), not a standalone
  inference pipeline.
- Results are **comparable across Yoker versions** — same model, same
  suite, different Yoker version → delta = Yoker's change.
- Efficiency metrics (tokens, latency, cost) are **first-class** alongside
  quality scores.
- The framework is **configuration-driven** — test suites are YAML +
  optional Python, the runtime is a small generic engine.

### 1.2 The Bidirectional Loop

```
                    yoker-test eval
                        │
           ┌────────────┴────────────┐
           ▼                         ▼
    Model Profiles              Score Deltas
    (quality + efficiency)      (regression signal)
           │                         │
           ▼                         ▼
  docs/model-compatibility.md   Bug reports / fixes in Yoker
           │                         │
           ▼                         ▼
  Users choose models         Yoker improves
           │                         │
           └────────────┬────────────┘
                        │
                        ▼
                  Re-run yoker-test
                  (with better Yoker)
```

### 1.3 The unittest Analogy

The architecture maps directly to Python's `unittest`:

| unittest | yoker-test |
|---|---|
| `TestRunner` | `EvalRunner` |
| `TestCase` / `test_*` methods | `TestTask` |
| `assertEqual(a, b)` | `scorer(task, response) → float` |
| `setUp` / `tearDown` | runtime config (temp=0, seed, repeats) |
| `TestSuite` | suite YAML |
| test discovery | suite loading (parse YAML, resolve `!function`) |
| pass/fail (boolean) | score 0.0–1.0 (graded) |
| test report | eval report (per-task, per-category, overall, with stats) |
| — | baseline comparison (regression detection) |

The conceptual difference is small: unittest tests Python code with boolean
assertions; yoker-test tests LLM responses through Yoker with float scorers
and quantitative metrics.

---

## 2. Architecture: Framework vs. Configuration

The core design principle is **strict separation** between the test runtime
framework (HOW to test) and the test suite configuration (WHAT to test).

```
Framework (runtime):  HOW to test    — send prompt, collect response, gather stats, aggregate
Configuration (suite): WHAT to test  — which prompts, how to score, what categories
```

The framework is a generic execution engine. It knows nothing about math
questions, multiple choice, or code generation. It only knows: "take a
prompt, send it to a model through Yoker, get a response back, apply a
scoring function, record everything."

The configuration brings the domain knowledge: the actual prompts, the
expected answers, the scoring logic. It can be as simple as a YAML file
with static tasks, or as rich as a Python module with dynamic task
generation and custom scorers.

### 2.1 Framework Core — What It Owns

The framework is responsible for exactly these things:

1. **Loading a configuration** — Parse YAML suite definition, resolve
   `!function` references to Python callables, validate well-formedness.
2. **Executing tests through Yoker** — For each task, send the prompt
   through `process()` or `backend.chat_stream()`. Collect response text,
   `UsageStats` (tokens, latency). Handle repeats and errors.
3. **Applying scorers** — Look up scorer by name (built-in) or use the
   provided callable (custom). Call `scorer(task, response) → float | Score`.
4. **Aggregating results** — Group by category, compute mean ± std, sum
   tokens/latency, compute cost, produce structured report.
5. **Baseline comparison (optional)** — Load a previous report, compute
   deltas per category and overall, flag regressions.
6. **Report output** — Serialize to YAML/JSON, optional human-readable
   summary.

The framework is deliberately ~300-400 lines of Python. It is a loop with
bookkeeping.

### 2.2 Configuration — What It Brings

The configuration is a suite definition specifying:

```
Suite Definition
├── Metadata: name, version, description
├── Runtime: temperature, seed, repeats, max_tokens
├── Tasks: the actual test cases
│   ├── Static: defined inline in YAML
│   └── Dynamic: generated by a Python function
├── Scorers: how to evaluate responses
│   ├── Built-in: referenced by name (exact_match, numeric_match, ...)
│   └── Custom: Python callables loaded from a module
└── Aggregation: how to combine scores (optional weights per category)
```

### 2.3 The Interface — Three Protocols

```python
# A task is what the framework executes
@dataclass
class TestTask:
    id: str
    category: str
    difficulty: str
    prompt: str
    expected: Any           # whatever the scorer needs
    scorer: str | Callable   # name of built-in, or a callable
    scorer_config: dict      # kwargs passed to the scorer
    system_prompt: str | None = None

# A scorer evaluates a response — returns a float or a richer Score
Scorer = Callable[[TestTask, str], float | Score]

# A task generator produces tasks dynamically
TaskGenerator = Callable[[dict], list[TestTask]]
```

The framework only needs these three things. Everything else is
configuration.

### 2.4 What the Framework Does NOT Do

- No prompt engineering — prompts come from the suite config
- No answer interpretation — the scorer handles that, scorers come from
  the config
- No dataset loading — if a suite needs external data, the task generator
  handles it
- No model selection — the caller specifies the model
- No benchmark comparison — it doesn't compare to MMLU or GSM8K scores from
  other frameworks
- No statistical significance testing — it reports mean ± std, the caller
  decides what's significant
- No LLM-as-judge — that's a custom scorer the suite config would provide;
  the framework just calls it

---

## 3. Data Structures

### 3.1 TestTask

```python
@dataclass
class TestTask:
    id: str
    category: str          # e.g. "knowledge", "reasoning", "code"
    difficulty: str        # "easy", "medium", "hard"
    prompt: str            # what to send to the model
    expected: Any          # what the scorer compares against
    scorer: str | Callable # built-in name or custom callable
    scorer_config: dict    # kwargs for the scorer
    system_prompt: str | None = None  # optional per-task system prompt
```

### 3.2 Score (scorer return type)

A scorer can return a bare float or a richer `Score` object:

```python
@dataclass
class Score:
    value: float                    # 0.0 - 1.0, the primary score
    extracted: str | None = None    # what was extracted from the response
    sub_scores: dict[str, float] | None = None  # e.g. per-test-case results
    explanation: str | None = None  # why this score (for debugging)
```

Simple scorers return `1.0`. Code execution scorers return
`Score(value=0.75, sub_scores={"test_1": 1.0, "test_2": 0.0})`. The
framework unpacks the `Score` into the `TestResult` fields.

### 3.3 TestResult

```python
@dataclass
class TestResult:
    # Identity
    task_id: str
    category: str
    difficulty: str
    repeat: int               # which repetition (0-indexed)

    # The exchange
    prompt: str               # what was sent
    response: str             # what came back
    messages: list[dict]      # full message exchange (if multi-turn)

    # Quantitative metrics (from Yoker's UsageStats + wall-clock)
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: float         # total time, prompt to completion
    ttft_ms: float | None      # time to first token (if streaming)

    # Quality (from the scorer)
    score: float              # 0.0 - 1.0
    scorer_name: str
    extracted: str | None     # what the scorer extracted
    sub_scores: dict[str, float] | None

    # Status
    error: str | None         # if the call failed
```

The framework collects everything except `score`, `scorer_name`,
`extracted`, `sub_scores`, and `error` automatically. The scorer adds the
quality dimension. Errors are caught by the framework.

### 3.4 TestReport

```python
@dataclass
class TestReport:
    # Run metadata
    run: RunMetadata
    # Per-task results (all repeats)
    results: list[TestResult]
    # Aggregated summary
    summary: dict[str, CategorySummary]  # keyed by category
    overall: OverallSummary
    # Optional baseline comparison
    comparison: ComparisonReport | None
    # Serialize
    def to_yaml(self) -> str: ...
    def to_json(self) -> str: ...
    def to_dict(self) -> dict: ...
```

---

## 4. Built-in Scorers

These are common scoring patterns provided by the framework, referenced by
name from YAML. They cover ~90% of scoring needs.

| Name | What It Does | Config |
|---|---|---|
| `exact_match` | Normalize both strings, compare | `ignore_case`, `ignore_punctuation` |
| `numeric_match` | Extract first number from response, compare with tolerance | `tolerance` |
| `regex_extract` | Apply regex, compare captured group | `pattern`, `group` |
| `contains` | Check if expected string appears in response | `ignore_case` |
| `mcq` | Extract letter A-D from response, compare | — |
| `json_valid` | Try `json.loads()`, optionally check keys | `required_keys` |
| `code_execution` | Extract code, exec in sandbox, run test cases | `test_cases`, `timeout` |

### 4.1 Answer Normalization

Adopted from OpenAI's `simple-evals` `normalize_response` function — strip
markdown and LaTeX formatting before comparison:

```python
def normalize_response(response: str) -> str:
    return (
        response.replace("**", "")
        .replace("$\\boxed{", "")
        .replace("}$", "")
        .replace("\\$", "")
        .replace("$\\text{", "")
        .replace("$", "")
        .replace("\\mathrm{", "")
        .replace("\\{", "")
        .replace("\\text", "")
        .replace("\\(", "")
        .replace("\\mathbf{", "")
        .replace("{", "")
        .replace("\\boxed", "")
    )
```

### 4.2 MCQ Answer Extraction

Multi-step fallback chain (first match wins), based on patterns observed
in the major frameworks:

```
1. Response is exactly one of A/B/C/D → use it
2. Regex: r'(?i)Answer[ \t]*:[ \t]*\$?([A-D])\$?' → use it
3. Regex: r'\b([ABCD])\b' on first line → use it
4. Regex: r'^([ABCD])\)' → use it (e.g., "B) Paris")
5. First standalone A/B/C/D in the response → use it
6. No match → score 0
```

### 4.3 Numeric Answer Extraction

```
1. Strip all non-numeric characters except . and -
2. Extract the first number (regex: r'-?[\d.]+')
3. Handle common formats: "36", "36.0", "$36", "36 degrees"
4. Convert to float
5. Compare with tolerance
```

### 4.4 Code Extraction

```
1. If ```python ... ``` in response → extract content between fences
2. If ``` ... ``` → extract content
3. Otherwise → use entire response (strip whitespace)
4. Exec in sandbox with timeout
5. Run test cases, score = cases_passed / total_cases
```

### 4.5 Custom Scorers

For domain-specific scoring, the configuration provides Python functions:

**In YAML (lm-eval style with `!function`):**
```yaml
tasks:
  - id: X1
    prompt: "..."
    expected: "some complex thing"
    scorer: !function my_suite.scorers.evaluate_x1
```

**In Python (direct):**
```python
suite = Suite(
    tasks=[
        TestTask(id="X1", prompt="...", expected="...", scorer=my_scorer),
    ]
)
```

The framework doesn't care. A scorer is a callable that takes
`(task, response)` and returns a float or `Score`. Whether it's a built-in
name, a `!function` reference, or a direct callable — same interface.

---

## 5. Quantitative Metrics & Efficiency

### 5.1 What Gets Collected Per Task

Two layers of data, collected by different actors:

**Framework-collected (automatic):**

| Metric | Source | Description |
|---|---|---|
| `tokens_in` | `UsageStats.input_tokens` / `prompt_eval_count` | Input tokens consumed |
| `tokens_out` | `UsageStats.output_tokens` / `eval_count` | Output tokens generated |
| `latency_ms` | Wall-clock (prompt → completion) | Total latency |
| `ttft_ms` | Wall-clock (prompt → first token) | Time to first token (if streaming) |

**Scorer-returned:**

| Metric | Source | Description |
|---|---|---|
| `score` | Scorer function | 0.0–1.0 quality score |
| `sub_scores` | Scorer function | Per-component scores (e.g., per test case) |
| `extracted` | Scorer function | What was extracted from the response |

### 5.2 Aggregated Report

The report is multi-dimensional, not just "average score":

```yaml
summary:
  knowledge:
    # Quality
    score: 0.875
    std: 0.0
    n_tasks: 8
    # Efficiency
    avg_tokens_in: 42
    avg_tokens_out: 3
    avg_latency_ms: 850
    total_tokens: 1080
    total_latency_s: 20.4
    # Cost (if pricing provided)
    cost: 0.0001
  reasoning:
    score: 0.625
    std: 0.05
    n_tasks: 8
    avg_tokens_in: 65
    avg_tokens_out: 120
    avg_latency_ms: 2800
    total_tokens: 7800
    total_latency_s: 67.2
    cost: 0.0008
  overall:
    score: 0.694
    std: 0.02
    total_tokens_in: 4200
    total_tokens_out: 1800
    total_tokens: 6000
    total_latency_s: 112.5
    avg_tokens_per_second: 16.0
    total_cost: 0.0023
    cost_per_correct_answer: 0.0033
```

### 5.3 Cost Model

The framework collects raw tokens and latency. Cost is a derived metric
requiring pricing data, which is external.

**Pricing file (maintained separately from suites):**

```yaml
# pricing.yaml — updated independently
models:
  llama3.2:3b:
    provider: ollama
    cost: 0.0                    # local = free
  gpt-4o-mini:
    provider: openai
    input_per_million: 0.15
    output_per_million: 0.60
  claude-3.5-sonnet:
    provider: anthropic
    input_per_million: 3.00
    output_per_million: 15.00
```

The framework loads pricing once at startup and computes:
`cost = (tokens_in × input_price + tokens_out × output_price) / 1_000_000`.

For Ollama (local), cost is 0.0 (free compute). For shared GPU or paid
compute, cost could be estimated as `latency_s × gpu_rate` — this is a
configuration choice, not a framework feature. The framework provides
the raw `latency_s`; the caller computes cost however they want.

### 5.4 Cost Per Correct Answer

A key derived metric for the "cheap vs expensive" differentiation:

```
cost_per_correct_answer = total_cost / (overall_score × n_tasks)
```

A cheap model that gets 70% right for $0.001 has a better
cost-per-correct-answer than an expensive model that gets 95% right for
$0.05.

---

## 6. Regression Testing

### 6.1 The Differential Approach

```
Yoker v1.0  +  Model X  +  Suite A  →  Score S1
Yoker v1.1  +  Model X  +  Suite A  →  Score S2

Δ = S2 - S1  →  indirect measure of Yoker's change
```

The model is the **fixed reference**. The suite is the **fixed probe**.
Yoker is the **variable**. Any score change is attributable to Yoker
because nothing else moved.

### 6.2 What the Delta Captures

| Dimension | If it drops, Yoker might have... | If it improves, Yoker might have... |
|---|---|---|
| Quality | Changed prompt formatting, broken system prompt handling, altered context construction, introduced a bug in tool calling | Improved prompt construction, better context handling, fixed a tool-call parsing bug |
| Latency | Added processing overhead, broken streaming efficiency | Optimized the processing pipeline, improved streaming |
| Token usage | Changed how context is built (adding/removing tokens), altered system prompt injection | Tightened context construction, reduced overhead tokens |
| Tool-use score | Broken tool argument parsing, changed tool schema generation | Fixed tool parsing, improved schema format for models |

### 6.3 Stored Baselines

Each eval run produces a result bundle keyed by (Yoker version, model,
suite version). These are stored. Next time, load the matching baseline
and compute deltas.

```yaml
# baselines/registry.yaml
- yoker_version: "1.0.0"
  suite_version: "1.0"
  model: llama3.2:3b
  quality: 0.66
  efficiency: 0.85
  composite: 0.72
  timestamp: 2025-01-10

- yoker_version: "1.1.0"
  suite_version: "1.0"
  model: llama3.2:3b
  quality: 0.64
  efficiency: 0.83
  composite: 0.69
  timestamp: 2025-01-20
  delta_from_previous:
    quality: -0.02
    efficiency: -0.02
    composite: -0.03
```

### 6.4 Reference Model Set

A small, fixed set of models that cover the main backend paths:

- One small Ollama model (e.g., `llama3.2:3b`) — fast, cheap, local,
  deterministic
- One larger Ollama model (e.g., `llama3.1:8b`) — more capable, still local
- One API model (e.g., `gpt-4o-mini`) — different backend path (LiteLLM)

If all three show the same delta, it's clearly Yoker, not a model fluke.

**Prefer Ollama models for regression baselines** — they're the only ones
that are truly deterministic (local execution, no silent model updates, no
batch non-determinism). API models can silently update, making baselines
unreliable over time.

### 6.5 Practical Workflow

```
Developer changes Yoker code
  → make check (existing tests pass)
  → yoker-test eval --model llama3.2:3b --suite yoker_basic
  → compare to stored baseline
  → if |delta| > threshold: investigate / fix / update baseline
  → if |delta| ≤ threshold: commit, baseline becomes new reference
```

Could be a Makefile target or CI step:

```makefile
eval-regression: ## Run model evaluation and compare to baseline
	uv run yoker-test eval --model llama3.2:3b --suite yoker_basic --compare baselines/latest.yaml
```

### 6.6 Noise Floor

With 30 graded prompts, the noise floor is roughly ±2-3 points (based on
graded scoring giving ~120 distinct score combinations). Changes of 3+
points are likely real. With 3 repeats per task, the prediction interval
width is typically < 0.01 (Blackwell et al. 2024).

---

## 7. Reliability

### 7.1 Sources of Non-Determinism

Research (Coqueret et al. 2026, Biderman et al. 2024, Blackwell et al.
2024, Tamba 2026) identifies five sources of non-determinism even at
temperature=0:

| Source | Survives T=0? | Controllable? |
|---|---|---|
| Deliberate sampling | No | Yes (set T=0) |
| Silent model updates | Yes | Only with local models |
| Floating-point rounding (batch size, hardware) | Yes | Only with local execution |
| Expert routing (MoE models) | Yes | Partially (local execution) |
| Server load / hardware differences | Yes | Only with local execution |

**Key finding**: Only local execution of open-weight models (e.g., Ollama)
gives fully deterministic results. API models will always have residual
non-determinism.

**Key finding**: Some newer models (Claude Opus 4.7/4.8) have deprecated
temperature entirely — the primary mitigation is being removed by
providers. The only robust mitigation that survives is statistical: run
epochs > 1 and report variance.

### 7.2 Mitigations

| Risk | Mitigation |
|---|---|
| Answer extraction failure | Multi-step extraction pipeline with fallback regexes, tested against real model outputs |
| Numeric edge cases | Tolerance-based comparison, handle multiple valid answers |
| Code extraction failure | Multiple fence format handling, fallback to raw response |
| Model non-determinism | Temperature=0, fixed seed, run N=3 repeats, report mean ± std |
| Suite contamination | Mix of standard questions + custom phrasings; version the suite |
| Scorer bugs | Unit-test the scorers against known model output samples |
| Prompt sensitivity | Fixed prompt template, no/fixed system prompt, same for all runs |
| API model silent updates | Prefer Ollama models for baselines; record model version + date |
| Borderline item flips | Inherent — report variance, don't treat as bugs |

### 7.3 Statistical Reporting

- Run each task **3 times** (Blackwell et al. show this is sufficient for
  prediction interval < 0.01 with temp=0)
- Report **mean ± std** per category and overall, not single point estimates
- For baseline comparison, flag deltas where **|delta| > 2 × std** as
  real regressions
- Adopt **bootstrap confidence intervals** (as lm-eval does by default)

### 7.4 What the Literature Says About Prompt Sensitivity

Biderman et al. (2024) document:
- Prompt formatting alone can change scores by **>20%** on the same model
- Different implementations of MMLU produce **different scores AND different
  model rankings**
- Single-run point estimates are misleading — GPQA scores for frontier
  models overlap significantly when 95% CIs are computed over 10 runs

**Implication**: Freeze prompts. Never change them without bumping the
suite version. Baselines are only comparable within the same suite version.

### 7.5 What the Literature Says About Answer Extraction

Biderman et al.: "different models may generate responses in varying
formats, making it challenging to create a universal regex pattern that
works for all models."

lm-eval-harness uses **dual filter pipelines** for GSM8K:
- `strict-match`: regex `"The answer is (\\-?[0-9\\.\\,]+)"` → take first
- `flexible-extract`: regex `"(-?[$0-9.,]{2,})|(-?[0-9]+)"` → take last

**Implication**: Our multi-step extraction pipeline with fallbacks is the
right approach. Consider reporting both strict and flexible scores (as
lm-eval does) so consumers can see the gap.

---

## 8. Comparison With Existing Frameworks

### 8.1 Feature Matrix

| Dimension | lm-eval-harness | simple-evals | lighteval | Inspect AI | **yoker-test** |
|---|---|---|---|---|---|
| Task format | YAML + Jinja2 | Python classes | Python dataclass | Python (Task/Sample/Scorer) | **YAML + `!function`** |
| Prompt style | Few-shot, variable | Zero-shot CoT | Configurable | Configurable | **Zero-shot, fixed** |
| Output type | Loglikelihood + generation | Generation only | Loglikelihood + generation | Generation + logprobs | **Generation only** |
| Scoring | Regex filters + exact_match | Regex + LLM equality | Custom functions | Built-in + custom scorers | **Multi-step extraction + graded** |
| Statistical rigor | Bootstrap CIs by default | Bootstrap std | Configurable | Clustered SEs, epochs | **Multiple runs, mean ± std** |
| Repeats | 1 (configurable) | 16 for MATH | Configurable | Epochs | **3 per task** |
| Determinism settings | temperature=0 in YAML | Not always set | Configurable | Configurable | **temperature=0, fixed seed** |
| Versioning | metadata.version in YAML | No | version field | No | **Suite version in YAML** |
| Backend | HF, vLLM, API | OpenAI, Anthropic | HF, vLLM, Inspect | Any provider | **Yoker backends** |
| Efficiency metrics | No | No | No | No | **Yes (tokens, latency, cost)** |
| Tool-use testing | No | No | No | Yes (agent tasks) | **Yes (planned)** |
| Regression testing | No | No | No | No | **Yes (baseline comparison)** |
| Runs through host framework | No | No | No | No | **Yes (through Yoker)** |

### 8.2 What We Adopt

**From lm-evaluation-harness:**
- YAML task definitions with versioning
- Regex filter chains for answer extraction
- Bootstrap confidence intervals
- Dual-filter approach (strict + flexible) for numeric extraction

**From simple-evals:**
- `normalize_response` function (strip markdown/LaTeX)
- Zero-shot CoT prompt template for MCQ
- Bootstrap std computation
- LLM equality checker concept (for future use)

**From Inspect AI:**
- Clean `Sample(input, target)` + `scorer` separation
- Clustered standard errors
- Epochs for repeated runs
- Sandboxed code execution

**From the reliability research:**
- Temperature=0 is necessary but not sufficient — run multiple times
- 3 runs is usually enough for prediction interval < 0.01
- Local models are the only truly deterministic ones — prefer for baselines
- Report mean ± std, not single point estimates
- Document everything: model version, provider, date, API endpoint

### 8.3 What Makes yoker-test Unique

1. **Runs through Yoker** — tests the actual pipeline, not just the model.
   No other framework tests their own infrastructure.
2. **Regression testing** — baseline comparison to detect Yoker changes.
   No other framework does this because they don't have a "host framework"
   to regress against.
3. **Efficiency metrics** — tokens, latency, tokens/sec, cost as first-class
   metrics. No other framework reports these alongside quality.
4. **Configuration-driven** — test suites are YAML + optional Python,
   framework is a small generic engine. Similar to unittest's separation
   of TestRunner from TestCase.

### 8.4 What We Don't Claim

- Our scores will **not match** lm-eval's MMLU scores or simple-evals' GPQA
  scores. Different prompts, different extraction, different scoring. This
  is expected and fine — as openbench states: "results are meant to be
  compared with results from the same framework."
- We are **not** building 1000+ tasks. A focused suite of ~30-65 tasks is
  the starting point.
- We are **not** building a leaderboard. The landscape overview is for
  Yoker users, not for the broader ML community.

---

## 9. Suite Configuration Format

### 9.1 Simple Case — Static Tasks, Built-in Scorers

```yaml
suite: yoker_basic
version: "1.0"
description: "Minimal model evaluation suite for Yoker"
repeats: 3
temperature: 0.0
seed: 42

tasks:
  - id: K1
    category: knowledge
    difficulty: easy
    prompt: |
      Question: What is the chemical symbol for gold?
      A) Gd  B) Go  C) Au  D) Ag
      Reply with only the letter.
    expected: "C"
    scorer: mcq

  - id: R1
    category: reasoning
    difficulty: easy
    prompt: "What is 15% of 240? Answer with just the number."
    expected: 36
    scorer: numeric_match
    scorer_config:
      tolerance: 0.01

  - id: I1
    category: instruction
    difficulty: easy
    prompt: "List exactly 3 fruits. Each on a new line prefixed with '- '."
    expected: 3
    scorer: !function yoker_basic.scorers.count_bullet_lines
```

### 9.2 Rich Case — Dynamic Generation, Custom Scorers

```yaml
suite: yoker_code_eval
version: "1.0"
repeats: 1
temperature: 0.0

task_generator: !function code_suite.generate_tasks
generator_config:
  difficulty: [easy, medium, hard]
  count: 20

scorers:
  code_execution:
    timeout: 5
    sandbox: restricted

aggregation:
  weights:
    easy: 0.2
    medium: 0.3
    hard: 0.5
```

### 9.3 The `!function` Resolution Mechanism

Similar to lm-eval-harness's `!function` operator. The loader resolves
`!function module.path.function` by importing the module and retrieving
the attribute. This allows suites to provide custom Python code (scorers,
generators) alongside their YAML configuration.

The resolution happens at suite load time, before any tests are executed.
If a function can't be resolved, the load fails with a clear error.

---

## 10. The Minimal Suite: yoker_basic v1.0

A focused set of ~30 tasks across 5 categories, designed to differentiate
models from ~40% (weak 3B) to ~90% (strong API model).

### 10.1 Category Distribution

| Category | Tasks | Scoring | Purpose |
|---|---|---|---|
| Knowledge | 8 | mcq (binary) | Factual knowledge, MCQ format |
| Reasoning | 8 | numeric_match (graded) | Math and logic, numeric answers |
| Instruction Following | 6 | structural (graded) | Format constraint compliance |
| Code Generation | 4 | code_execution (graded) | Write and verify Python code |
| Tool Use | 4 | tool_call_verify (graded) | Emit and parse tool calls |
| **Total** | **30** | | |

### 10.2 Difficulty Distribution

Each category has a mix of easy, medium, and hard tasks:

- **Easy**: all models should get these right (~90%+). If missed, either
  the model is very weak or Yoker's prompt formatting broke.
- **Medium**: mid-tier models start missing some. This is where
  differentiation begins.
- **Hard**: only strong models succeed. This separates the top tier.

### 10.3 Graded Scoring

Binary scoring (0/1) with 30 prompts gives ~3.3% resolution per prompt.
Graded scoring (0, 0.25, 0.5, 0.75, 1.0) gives ~120+ distinct combinations.
This detects finer shifts — a model that was getting 0.75 on a code task
(3/4 test cases) and now gets 0.50 (2/4) is a detectable change even though
binary scoring would show no difference.

### 10.4 Expected Score Spread

| Model | Knowledge (8) | Reasoning (8) | Instr. (6) | Code (4) | Tools (4) | Total | % |
|---|---|---|---|---|---|---|---|
| 3B model | 5 | 3 | 2 | 1 | 1 | 12 | 40% |
| 7B model | 6 | 4 | 3 | 2 | 2 | 17 | 57% |
| 70B model | 7 | 6 | 4 | 3 | 3 | 23 | 77% |
| GPT-4o | 8 | 7 | 5 | 3.5 | 3.5 | 27 | 90% |

This 40%–90% spread is what makes the suite meaningful — not too easy, not
too hard.

### 10.5 Task Format (YAML)

```yaml
suite: yoker_basic
version: "1.0"
description: "Minimal model evaluation suite for Yoker regression testing"
repeats: 3
temperature: 0.0
seed: 42

tasks:
  # Knowledge (8)
  - id: K1
    category: knowledge
    difficulty: easy
    prompt: |
      Question: What is the chemical symbol for gold?
      A) Gd
      B) Go
      C) Au
      D) Ag
      Reply with only the letter of the correct answer.
    expected: "C"
    scorer: mcq

  # ... 29 more tasks

aggregation:
  weights:
    knowledge: 0.25
    reasoning: 0.25
    instruction: 0.20
    code: 0.15
    tool_use: 0.15
```

---

## 11. Report Format

### 11.1 Full Report

```yaml
run:
  suite: yoker_basic
  suite_version: "1.0"
  model: llama3.2:3b
  provider: ollama
  yoker_version: 0.10.1
  temperature: 0.0
  seed: 42
  repeats: 3
  timestamp: 2025-01-15T10:30:00Z

results:
  - task_id: K1
    category: knowledge
    difficulty: easy
    repeat: 0
    score: 1.0
    response: "C"
    tokens_in: 42
    tokens_out: 3
    latency_ms: 850
    scorer: mcq
    extracted: "C"
  - task_id: K1
    repeat: 1
    score: 1.0
    ...
  - task_id: R1
    category: reasoning
    repeat: 0
    score: 1.0
    response: "150"
    tokens_in: 28
    tokens_out: 5
    latency_ms: 1200
    scorer: numeric_match
    extracted: "150"
  ...

summary:
  knowledge:
    score: 0.875
    std: 0.0
    n_tasks: 8
    avg_tokens_in: 40
    avg_tokens_out: 4
    avg_latency_ms: 900
    total_tokens: 1080
    total_latency_s: 20.4
    cost: 0.0
  reasoning:
    score: 0.625
    std: 0.05
    n_tasks: 8
    avg_tokens_in: 65
    avg_tokens_out: 120
    avg_latency_ms: 2800
    total_tokens: 7800
    total_latency_s: 67.2
    cost: 0.0
  instruction:
    score: 0.583
    std: 0.03
    n_tasks: 6
    ...
  code:
    score: 0.250
    std: 0.08
    n_tasks: 4
    ...
  tool_use:
    score: 0.250
    std: 0.06
    n_tasks: 4
    ...

overall:
  score: 0.536
  std: 0.02
  total_tokens_in: 4200
  total_tokens_out: 1800
  total_tokens: 6000
  total_latency_s: 112.5
  avg_tokens_per_second: 16.0
  total_cost: 0.0
  cost_per_correct_answer: 0.0

# Only present if --compare was given
comparison:
  baseline:
    yoker_version: 0.9.0
    timestamp: 2025-01-10T08:00:00Z
  delta:
    knowledge: 0.0       # stable
    reasoning: -0.125    # regression! investigate
    instruction: +0.04   # improvement
    code: +0.0
    tool_use: -0.25      # regression! tool parsing may be broken
    overall: -0.03
  flagged: [reasoning, tool_use]  # |delta| > 2 × std
```

### 11.2 Landscape Overview

Aggregated across multiple models, the report can be compiled into a
compatibility table:

```markdown
# Yoker Model Compatibility

## Ollama Models

| Model | Quality | Efficiency | Tool Use | Cost | Recommended For |
|-------|---------|------------|---------|------|----------------|
| llama3.2:3b | ★★★☆☆ | ★★★★★ | ✅ | free | Simple tasks, local |
| llama3.1:8b | ★★★★☆ | ★★★★☆ | ✅ | free | General purpose, local |

## API Models

| Model | Quality | Efficiency | Tool Use | Cost/Eval |
|-------|---------|------------|---------|----------|
| gpt-4o-mini | ★★★★☆ | ★★★★☆ | ✅ | $0.02 |
| gpt-4o | ★★★★★ | ★★★☆☆ | ✅ | $0.15 |

## Known Issues

- **qwen2.5:7b on Ollama**: `prompt_eval_count` occasionally returns None
  on first call. Yoker handles this gracefully (falls back to 0).
```

This document is both the output of the eval system and the input for
Yoker's documentation. When a new model is released, run `yoker-test eval`,
generate a profile, and update the compatibility table.

---

## 12. The Framework's Execution Loop

```
Load suite config
  → parse YAML
  → resolve !function references to Python callables
  → if task_generator: call it → get tasks
  → else: use static tasks from YAML
  → for each task: resolve scorer (built-in name → function, or use callable)
  → load pricing data (if provided)

For each task × repeat:
  → record start time
  → send task.prompt through Yoker (process() or backend.chat_stream())
  → collect: response text, UsageStats (tokens_in, tokens_out, total_duration_ms)
  → record end time → compute latency_ms, ttft_ms
  → call scorer(task, response) → score (float or Score object)
  → unpack Score → score, extracted, sub_scores
  → compute cost from tokens × pricing
  → assemble TestResult
  → handle errors (timeout, API error → error string, score = 0.0)

Aggregate:
  → group results by category
  → per category: mean score, std, avg tokens, avg latency, total cost
  → overall: weighted mean (weights from config or uniform)
  → total tokens, total latency, avg tokens/sec, total cost, cost per correct answer

Compare (if baseline provided):
  → load baseline report
  → compute delta per category and overall
  → flag if |delta| > threshold (e.g., 2 × std)

Output report (YAML/JSON + optional human summary)
```

---

## 13. Module Structure

### 13.1 yoker-test Package

```
yoker-test/                     # standalone package
├── pyproject.toml              # depends on yoker (as SDK)
├── src/yoker_test/
│   ├── __init__.py             # Public API: evaluate(), EvalRunner, TestTask, TestReport
│   ├── schema.py               # TestTask, TestResult, TestReport, SuiteConfig dataclasses
│   ├── runner.py               # EvalRunner — the execution loop (~200-300 lines)
│   ├── scorers.py              # Built-in scorers (mcq, exact_match, numeric_match, ...)
│   ├── loader.py               # Load suite YAML, resolve !function references
│   ├── report.py               # Aggregate results, format report, compare baselines
│   ├── pricing.py              # Load pricing data, compute cost from tokens
│   └── cli.py                  # `yoker-test` CLI (thin wrapper around runner)
├── suites/                     # Built-in test suites (configuration, not framework code)
│   ├── yoker_basic/
│   │   ├── suite.yaml           # Task definitions + metadata
│   │   ├── scorers.py           # Custom scorers (optional)
│   │   └── generators.py        # Custom task generators (optional)
│   └── yoker_code/
│       ├── suite.yaml
│       └── scorers.py
├── baselines/                  # Stored baselines for regression comparison
│   └── registry.yaml
└── tests/                      # Tests for the framework itself
    ├── test_runner.py
    ├── test_scorers.py
    └── test_loader.py
```

### 13.2 Relationship to Yoker

```
yoker (SDK)                      yoker-test (package)
├── process()                    ├── evaluate()
├── Agent.process()              ├── EvalRunner
├── backend.chat_stream()        │   └── uses process() or backend
├── UsageStats                   ├── TestTask / TestResult / TestReport
└── Config                       └── SuiteConfig
```

yoker-test depends on yoker as a Python SDK. It uses:
- `yoker.process()` — one-shot prompt → response (no tools, no system prompt
  by default)
- `yoker.Agent` — for tool-use tasks that need an agent with tools
- `yoker.backends.protocol.UsageStats` — for token/latency collection
- `yoker.Config` — for model/provider configuration

yoker-test does NOT depend on Yoker's CLI, UI, session management, or
plugin system. It uses the SDK layer only.

### 13.3 Key Design Decision: Standalone Package

yoker-test is a **standalone package** with a dependency on yoker (as
SDK), not a submodule of yoker. This is because:

1. **Separation of concerns** — yoker is an agent harness; yoker-test is
   a test framework. Different audiences, different release cycles.
2. **yoker stays lean** — the eval framework is not needed by most yoker
   users. Adding it to the core package would bloat the dependency tree.
3. **Independent versioning** — yoker-test can release independently of
   yoker. The suite versions are independent of both yoker and yoker-test
   versions.
4. **Third-party suites** — someone could write a domain-specific eval
   suite (e.g., `medical-eval`) and run it through yoker-test without
   modifying either yoker or yoker-test.

---

## 14. Public API

### 14.1 Python API

```python
from yoker_test import evaluate, EvalRunner, TestTask, TestReport, Score

# Simple: load suite from YAML, run against a model
report = await evaluate(
    suite="yoker_basic",       # name or path to suite YAML
    model="llama3.2:3b",       # model to test
    compare="baseline.yaml",   # optional baseline to compare against
)

# Or: build a suite programmatically
report = await EvalRunner(
    tasks=[
        TestTask(id="K1", prompt="...", expected="C", scorer="mcq"),
        TestTask(id="R1", prompt="...", expected=36, scorer="numeric_match"),
    ],
    repeats=3,
    temperature=0.0,
).run(model="llama3.2:3b")

# Report is a structured object
print(report.overall.score)          # 0.694
print(report.summary["reasoning"])   # CategorySummary(...)
print(report.comparison.delta)       # {"reasoning": -0.125, ...}

# Serialize
report.to_yaml()                     # → YAML string
report.to_json()                     # → JSON string
```

### 14.2 CLI

```bash
# Run a suite against a model
yoker-test eval --suite yoker_basic --model llama3.2:3b

# Run and compare to a baseline
yoker-test eval --suite yoker_basic --model llama3.2:3b --compare baseline.yaml

# Run a custom suite
yoker-test eval --suite suites/custom/ --model gpt-4o-mini --output report.yaml

# List available suites
yoker-test suites

# Show a suite's tasks without running
yoker-test show --suite yoker_basic
```

---

## 15. Integration With Yoker's Backend Layer

### 15.1 How Tests Run Through Yoker

The eval runner sends prompts through Yoker's actual backend pipeline:

**For standard tasks (no tools):**
```python
# Uses yoker.process() — one-shot, no tools, no system prompt
response = await yoker.process(
    prompt=task.prompt,
    model=model,
    config=config,  # temperature=0, seed=42
)
```

**For tool-use tasks:**
```python
# Uses yoker.agent() with specific tools enabled
agent = yoker.agent(model=model, tools=["calculator", "search"])
response = await agent.process(task.prompt)
# Inspect agent's event stream for ToolCallDelta events
```

**For direct backend access (if needed):**
```python
# Uses yoker's ModelBackend directly — full control
async for chunk in backend.chat_stream(
    model=model,
    messages=[{"role": "user", "content": task.prompt}],
):
    if chunk.event == ChatChunkEvent.CONTENT_DELTA:
        response += chunk.text
    elif chunk.event == ChatChunkEvent.USAGE:
        tokens_in = chunk.usage.input_tokens
        tokens_out = chunk.usage.output_tokens
```

### 15.2 UsageStats Mapping

Yoker's `UsageStats` is provider-neutral:

```python
# From backends/protocol.py
class UsageStats:
    input_tokens: int | None = None       # OpenAI/Anthropic
    output_tokens: int | None = None       # OpenAI/Anthropic
    prompt_eval_count: int | None = None   # Ollama native (== input_tokens)
    eval_count: int | None = None          # Ollama native (== output_tokens)
    total_duration_ms: int | None = None   # Ollama native total duration
```

The eval framework normalizes:

```python
tokens_in = usage.input_tokens or usage.prompt_eval_count or 0
tokens_out = usage.output_tokens or usage.eval_count or 0
latency_ms = usage.total_duration_ms or wall_clock_ms
```

---

## 16. Phasing

| Phase | Scope | Output |
|---|---|---|
| **Phase 1** | Core runner + 6 built-in scorers + yoker_basic suite (30 tasks) + basic report + baseline comparison | Can score any Ollama/API model on quality + efficiency, detect Yoker regressions |
| **Phase 2** | Tool-use evaluation + multi-turn context tests + statistical significance + variance reporting | Full agentic capability profile |
| **Phase 3** | Cross-backend comparison (same model, different Yoker backend) + auto-generated compatibility docs | Adapter bug detection, living documentation |
| **Phase 4** | LLM-as-judge scorer (optional) + custom task generators + suite marketplace | Domain-specific evals, community suites |

---

## 17. Open Questions

1. **Should yoker-test live in the same repo as yoker, or a separate repo?**
   Recommendation: separate repo, separate package. Different audiences and
   release cycles.

2. **How to handle models that refuse to answer?** Some models will refuse
   certain prompts (safety filters). Should this count as "wrong" or be a
   separate "refused" category? Recommendation: record as error, score 0.0,
   flag in report as "refused" if detected.

3. **Streaming vs. non-streaming?** For eval, we want the full response, so
   collect all chunks. But latency measurement should include TTFT and
   total generation time separately.

4. **How to handle pricing updates?** Pricing changes frequently. The
   pricing file is external and versioned separately. Old reports keep
   their computed cost; re-running with updated pricing may change cost
   numbers (but not quality numbers).

5. **Should we support running existing lm-eval-harness tasks?** Could be
   an adapter that imports task definitions. Risk: complexity, dependency
   on external data. Recommendation: not in Phase 1. The `!function`
   mechanism allows users to write their own adapters if needed.

6. **Multi-turn evaluation?** Phase 1 is single-turn. Phase 2 adds
   multi-turn (send turn 1, then turn 2 referencing turn 1, verify model
   "remembers"). This tests Yoker's context handling.

7. **Thinking mode?** Some models support thinking/reasoning. Should the
   suite test with thinking on/off? Recommendation: default off, optional
   per-task override in suite config.