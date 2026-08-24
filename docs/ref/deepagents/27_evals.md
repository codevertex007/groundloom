# Document 27 -- Evaluation Framework

## Purpose and Scope

The evals package provides an end-to-end evaluation framework for Deep Agents, covering:

1. **Sandbox execution** -- running agents inside isolated Harbor environments.
2. **Result tracking** -- recording outcomes in LangSmith with deterministic example IDs.
3. **Failure analysis** -- distinguishing infrastructure failures from capability failures.
4. **Statistical reporting** -- confidence intervals and minimum detectable effects.
5. **Visualization** -- radar charts comparing model performance across categories.
6. **CI integration** -- GitHub Actions summary tables and exit codes.

The framework separates evaluation noise from infrastructure failures (OOM, timeouts, sandbox crashes) so that benchmark scores reflect genuine model capability differences.

> **Source packages** (`libs/evals/`): `deepagents_evals/` (CLI + visualization),
> `deepagents_harbor/` (LangSmith integration + the `langgraph_project/` agent),
> `deepagents_clbench/` (CL-bench system), and `harbor_adapters/contextbench/`
> (ContextBench adapter).
> **CLI entry point**: `deepagents-evals`

---

## Package Structure

> **Changed since the previous docs:** the Harbor layer was refactored. The old
> `backend.py` (HarborSandbox), `deepagents_wrapper.py` (DeepAgentsWrapper), and
> `metadata.py` were **removed**; agent construction now lives in
> `deepagents_harbor/langgraph_project/` (`langgraph_agent.py` + `langgraph.json`).
> Two additional code trees were added: `deepagents_clbench/` and
> `harbor_adapters/contextbench/`. The sections below that describe
> `HarborSandbox`/`DeepAgentsWrapper` are historical and no longer match the tree.

The system spans four code trees within `libs/evals/`:

### deepagents_harbor -- LangSmith + Agent Layer

| Module                  | Purpose                                              |
|-------------------------|------------------------------------------------------|
| `langgraph_project/`    | Agent construction (`langgraph_agent.py`, `langgraph.json`) |
| `langsmith.py`          | Dataset/experiment/feedback lifecycle                |
| `failure.py`            | FailureCategory classification                       |
| `stats.py`              | Wilson CI + minimum detectable effect                |

### deepagents_evals -- CLI and Visualization

| Module               | Lines | Purpose                                              |
|----------------------|-------|------------------------------------------------------|
| `cli.py`             | 726   | Unified CLI with 7 subcommands                       |
| `radar.py`           | 539   | Radar chart generation (light/dark themes)           |
| `trial_summary.py`   | 66    | GitHub Actions markdown summary tables               |
| `tau3_subset.py`     | —     | tau3 benchmark subset selection                      |

### Other code trees

| Path | Purpose |
|------|---------|
| `deepagents_clbench/` | CL-bench system (`system/system.py`) |
| `harbor_adapters/contextbench/` | ContextBench adapter (`adapter.py`, `main.py`, vendored data) |

### Supporting Assets

| Path                        | Purpose                                           |
|-----------------------------|---------------------------------------------------|
| `categories.json`           | Eval categories and radar-eligible subset          |
| `benchmark_samples/`        | External benchmark data (BFCL, FRAMES, NEXUS)     |
| `scripts/run_trials.py`     | CI trial runner with aggregation                   |

---

## HarborSandbox -- Sandboxed Execution (`backend.py`)

`HarborSandbox` implements `SandboxBackendProtocol` for running agent commands inside isolated Harbor environments:

```python
DEFAULT_COMMAND_TIMEOUT_SEC = 300
```

Key operations (all async-only -- sync methods raise `NotImplementedError`):

- **`aexecute(command, timeout)`** -- runs a shell command in the sandbox. If the command exceeds the timeout, the sandbox returns a descriptive error with suggestions for optimization.
- **File operations** -- `aread_file()`, `awrite_file()`, `aedit_file()` operate within the sandbox filesystem.
- **Lifecycle** -- `astart()` provisions the sandbox, `astop()` tears it down.

The timeout handling is notable: rather than raising a raw `TimeoutError`, the sandbox returns a structured message suggesting the agent break the task into smaller steps. This improves agent self-correction behavior. For the general backend protocol, see [10_backends.md](./10_backends.md).

---

## DeepAgentsWrapper -- Harbor Agent Bridge (`deepagents_wrapper.py`)

`DeepAgentsWrapper` extends Harbor's `BaseAgent` to run a full Deep Agents graph inside the evaluation harness:

```python
SYSTEM_MESSAGE = """You are an expert software engineer...
Working directory: {working_dir}
"""
```

Key features:

- Uses `create_deep_agent` and `create_cli_agent` to build the agent graph, the same builders used by `deepagents-code` (see [25_code_agent.md](./25_code_agent.md)).
- Injects the working directory into the system message so the agent operates in the correct sandbox path.
- Supports **OpenRouter** providers via `_parse_openrouter_providers()`, which extracts provider routing preferences from model IDs.
- Connects the `HarborSandbox` as the backend instead of `LocalShellBackend`, ensuring all tool execution happens within the isolated sandbox.

For the core graph builder, see [06_graph.md](./06_graph.md). For the middleware stack used by the wrapper, see [11_middleware.md](./11_middleware.md).

---

## CLI Subcommands (`cli.py`)

The `deepagents-evals` CLI provides seven subcommands:

| Subcommand     | Purpose                                                        |
|----------------|----------------------------------------------------------------|
| `run`          | Execute an evaluation suite against a model configuration.     |
| `trials`       | Run multiple trials of the same evaluation for significance.   |
| `aggregate`    | Combine results from multiple runs into a summary.             |
| `radar`        | Generate radar charts comparing model performance.             |
| `catalog`      | List available evaluation benchmarks and categories.           |
| `model-groups` | Display configured model group definitions.                    |
| `list`         | List completed experiments and their metadata.                 |

### Exit Codes

```python
# Exit code conventions
0  # OK -- all evaluations passed
1  # Failures detected in evaluation results
2  # Configuration error (bad args, missing config)
3  # No reports generated (nothing to aggregate)
```

### Known Tiers

```python
_KNOWN_TIERS = ("baseline", "hillclimb")
```

Tiers organize evaluation runs into categories. A `baseline` run establishes reference scores; `hillclimb` runs test improvements against the baseline. This tiered approach supports A/B comparison workflows in CI.

---

## Trial Runner (`scripts/run_trials.py`)

The trial runner executes multiple independent trials and aggregates scalar metrics:

```python
@dataclass
class _Stats:
    n: int
    mean: float
    median: float
    stdev: float
    min: float
    max: float

_SCALAR_METRICS = (
    "correctness",
    "solve_rate",
    "step_ratio",
    "tool_call_ratio",
    "median_duration_s",
)

_MAX_TRIALS = 50
```

Trials run sequentially (not in parallel) to avoid resource contention in the sandbox environment. After all trials complete, the runner computes per-metric statistics and outputs a summary table suitable for CI reporting.

### Metric Definitions

| Metric               | Description                                                    |
|----------------------|----------------------------------------------------------------|
| `correctness`        | Binary score from the LLM judge (correct / incorrect).         |
| `solve_rate`         | Fraction of tasks the agent solved completely.                 |
| `step_ratio`         | Ratio of agent steps to reference solution steps.              |
| `tool_call_ratio`    | Ratio of tool calls to reference solution tool calls.          |
| `median_duration_s`  | Median wall-clock time per evaluation task.                    |

---

## Failure Classification (`failure.py`)

The `FailureCategory` system distinguishes infrastructure failures from capability failures:

- **Infrastructure failures** -- sandbox OOM, timeout, network errors, container crashes. These are excluded from capability metrics because they reflect environment problems, not model limitations.
- **Capability failures** -- the agent produced an incorrect answer, failed to complete the task, or made a logical error. These count toward the model's score.

This separation is critical for reliable benchmarking. Without it, a flaky sandbox would contaminate scores and make it impossible to measure genuine model improvements.

---

## LangSmith Integration (`langsmith.py`)

The LangSmith module manages the full lifecycle of evaluation data:

- **`create_dataset()`** -- creates a LangSmith dataset for evaluation inputs.
- **`ensure_dataset()`** -- idempotent dataset creation (creates only if missing).
- **`create_example_id_from_instruction()`** -- generates deterministic UUIDs from instruction text, ensuring the same task always maps to the same example ID across runs.
- **`create_experiment()`** -- creates an experiment record linked to a dataset.
- **`add_feedback()`** -- attaches evaluation scores (from the LLM judge or automated metrics) to experiment runs.

The deterministic example ID generation is important for longitudinal tracking: when the same benchmark task is evaluated across multiple models or time periods, results can be correlated without manual mapping.

---

## Radar Charts (`radar.py`)

The radar chart generator creates visual comparisons of model performance across evaluation categories. Features:

- **Dual theme support** -- generates both light and dark variants.
- **Category-aware** -- reads `categories.json` to determine which metrics to include on the radar.
- **Multi-model overlay** -- displays multiple models on the same chart for side-by-side comparison.
- **Score normalization** -- maps raw metric values to a 0-1 scale for consistent visualization.

---

## CI Integration

### GitHub Actions Summary (`trial_summary.py`)

Generates markdown tables suitable for GitHub Actions `$GITHUB_STEP_SUMMARY`:

```markdown
| Metric        | Mean  | Median | Stdev | Min   | Max   |
|---------------|-------|--------|-------|-------|-------|
| correctness   | 0.85  | 0.87   | 0.03  | 0.80  | 0.90  |
| solve_rate    | 0.72  | 0.74   | 0.04  | 0.65  | 0.78  |
```

### Exit Code Integration

The CLI's exit codes enable CI gates:
- Exit 0: pipeline continues.
- Exit 1: regression detected, pipeline can be configured to fail.
- Exit 2: configuration error, treated as a CI infrastructure failure.
- Exit 3: no data produced, may indicate a broken test suite.

---

## Benchmark Data

The `benchmark_samples/` directory contains external benchmark datasets:

| Dataset  | Domain                                                    |
|----------|-----------------------------------------------------------|
| BFCL     | Berkeley Function Calling Leaderboard -- tool use accuracy|
| FRAMES   | Multi-step reasoning with tool chains                     |
| NEXUS    | Complex agentic task completion                           |

These datasets provide standardized inputs for evaluating agent capabilities across different dimensions. The eval framework loads them as LangSmith datasets and runs the agent against each example in an isolated sandbox.

---

## Relationship to Other Packages

| Package            | Relationship                                                               |
|--------------------|----------------------------------------------------------------------------|
| `deepagents`       | Core SDK. The wrapper uses `create_deep_agent` for graph construction. See [06_graph.md](./06_graph.md). |
| `deepagents-code`  | The wrapper uses `create_cli_agent` for agent construction. See [25_code_agent.md](./25_code_agent.md). |
| `deepagents-acp`   | Not directly related; both consume the same SDK. See [23_acp_server.md](./23_acp_server.md). |
| `deepagents-talon` | Not directly related; both use sandbox backends. See [26_talon.md](./26_talon.md). |
| `deepagents-cli`   | Deployment tooling. See [24_cli_deploy.md](./24_cli_deploy.md). |

The evals package is the quality gate for the Deep Agents ecosystem. It validates that changes to the core SDK, middleware, or tool implementations do not regress agent performance, using sandboxed execution to ensure reproducibility and failure classification to ensure accuracy.
