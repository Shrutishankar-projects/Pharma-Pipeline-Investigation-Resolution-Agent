# Pharma Agentic Pipeline Investigator

An enterprise-style Agentic AI prototype that investigates failed/anomalous
pharmaceutical pipeline runs, correlates evidence across logs, data quality,
schema, and approved documentation, proposes a root cause, and pauses for
human approval before any (simulated) corrective action.

The primary demonstration pipeline is a synthetic **Clinical Trial Data
Processing Pipeline** (`CLINTRIAL_ETL`), covering: Clinical Trial Source Data
-> Data Ingestion -> Data Quality Validation -> Data Transformation ->
Clinical Metrics Processing -> Validation -> Clinical Reporting Output.

**All data in this project is synthetic.** No real production systems,
patient data, or credentials are used or referenced anywhere.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate   # optional, if not already in a venv
pip install -r requirements.txt
cp .env.example .env                                  # defaults already work with no keys
streamlit run app/streamlit_app.py
```

Open the printed local URL (default `http://localhost:8501`). On page 1,
pick a run (the failing `CLINTRIAL_ETL` run `2026-10-30-001` is the primary
demo scenario) and click **Start Investigation**.

Run the test suite and the evaluation harness:

```bash
pytest -q
python -m evaluation.evaluator
```

## Demo scenario

> "Investigate the failed Clinical Trial Data Processing Pipeline run
> 2026-10-30-001. Identify the likely cause, provide supporting evidence,
> check relevant documentation, and recommend the next action."

Run `2026-10-30-001` fails at the **Data Transformation** stage because the
upstream EDC (Electronic Data Capture) source began sending qualified/
censored lab values (`"BLQ"`, `"<0.05"`, `"ND"`) as free text in
`lab_result_value` -- a FLOAT column -- instead of using a dedicated
qualifier flag, alongside a newly added `lab_qualifier_code` column. This is
a realistic clinical-data schema-drift failure (see
`data/documents/SOP-101_schema_change_management.md`).

Walking through the 7 UI pages for this run demonstrates the full mandated
sequence: UNDERSTAND → PLAN → DELEGATE → SKILL → TOOL/MCP → EVIDENCE →
REASON → OBSERVE → VERIFY → RE-PLAN → GUARDRAIL → HUMAN APPROVAL → EXECUTE →
VALIDATE → COMPLETE → EVALUATE → TRACE.

Four other synthetic runs cover the remaining evaluation scenarios (data
quality failure, infrastructure failure, insufficient evidence, and an
unsafe request) -- see `evaluation/scenarios/`.

| Run ID | Scenario |
|---|---|
| `2026-10-02-001` | Insufficient evidence (truncated log, no previous run on record) |
| `2026-10-09-001` | Infrastructure failure (EDC source connection timeout) |
| `2026-10-16-001` | Data quality failure (null `site_id` / duplicate `record_id`) |
| `2026-10-23-001` | Baseline successful run |
| `2026-10-30-001` | Schema change (primary demo, see above) |

## Capstone requirement -> implementation map

| # | Requirement | Where |
|---|---|---|
| 1 | CLAUDE.md | `CLAUDE.md` (this build follows it end to end) |
| 2 | Skills | `skills/*/core.py` -- 6 independently-testable skills, each with its own `test_core.py` |
| 3 | Hooks | `hooks/pre_agent.py`, `hooks/pre_tool.py`, `hooks/post_tool.py`, `hooks/workflow_hooks.py` -- wired into every node in `workflow/graph.py`, not decorative (they can block execution) |
| 4 | Sub-agents | `agents/supervisor.py` + `agents/{pipeline,data_quality,knowledge,root_cause,validation}_agent.py` |
| 5 | MCP | `mcp_server/server.py` (official `mcp` SDK, `MCPServer`) + `mcp_server/client.py` (the only path agents use to reach data) -- see naming note below |
| 6 | State / Context / Memory | `state/models.py` -- `InvestigationState`, a Pydantic LangGraph state schema with every field listed in CLAUDE.md section 14 |
| 7 | Guardrails | `guardrails/rules.py` (evidence, source, prompt-injection, hallucination, data-protection, execution) + `guardrails/authorization.py` (per-agent tool allowlist) |
| 8 | AI Governance | This README + inline docstrings; synthetic-only data (`data/`), no hard-coded secrets (`.env.example`), least-privilege tool access (`guardrails/authorization.py`), full accountability trail (`observability/`) |
| 9 | Human-in-the-Loop | `workflow/graph.py` `human_approval_node` -- a real LangGraph `interrupt()`/`Command(resume=...)` pause, UI page 5 |
| 10 | Evaluation | `evaluation/scenarios/*.json` (5 scenarios) + `evaluation/evaluator.py` + `evaluation/metrics.py`, UI page 7 |
| 11 | Observability | `observability/logger.py` (structured JSON logs, secret-scrubbing) + `observability/tracer.py` |
| 12 | Traceability | Every state carries one `trace_id`; every step appends a trace entry (`state.trace`); UI page 6 |

## Architecture

```
Streamlit UI (app/streamlit_app.py)
        |
Supervisor (agents/supervisor.py)  -- plan, delegate, final report
        |
LangGraph workflow (workflow/graph.py)
        |
   +----+----+----+----+----+
   |    |    |    |    |    |
Pipeline DataQuality Knowledge RootCause Validation   Agents
   |    |    |
   +----+----+----------------------------+
        |  every data-access call goes through:
   mcp_server/client.py  (Pre-Tool Hook -> authorization + input validation)
        |
   mcp_server/server.py  (official `mcp` SDK: MCPServer.call_tool)
        |
   skills/*/core.py  (independently testable, pure functions)
        |
   tools/*.py  (read-only access to data/*, synthetic fixtures only)
```

Guardrails (`guardrails/rules.py`) run at the `guardrail_check` node before
any high-impact action is proposed for human approval. Every node is wrapped
with the Pre-Agent Hook and a fail-safe error boundary (`workflow/graph.py:
_guarded`) so a single failure marks the workflow `FAILED` rather than
crashing or silently continuing (CLAUDE.md section 22).

### Re-planning

If `pipeline_agent`'s first pass produces no usable error evidence (e.g. a
truncated log), the workflow's conditional edge routes to a
`replan_previous_run` step that compares the run against its previous
attempt (`agents/pipeline_agent.compare_with_previous`) before continuing --
a genuine plan change at runtime, not a fixed linear chain (CLAUDE.md
section 23). See `evaluation/scenarios/scenario_4_insufficient_evidence.json`.

### LLM provider

`llm/provider.py` defines an `LLMProvider` interface selected via the
`LLM_PROVIDER` env var. The default, `deterministic`, is a fully offline,
zero-cost, zero-external-call template provider -- this build runs with no
API key. An `anthropic` provider is stubbed in (requires
`ANTHROPIC_API_KEY`) so a live model could be enabled later without
changing any agent code.

## Documented deviation from the suggested structure

CLAUDE.md section 24 suggests naming the MCP layer's folder `mcp/`. That
name collides with the real `mcp` PyPI package (the actual Model Context
Protocol SDK) required by section 13, once the project root is on
`sys.path` for the rest of the app's packages -- a local `mcp/` package
would shadow the installed library it needs to `import`. This directory is
named **`mcp_server/`** instead; its responsibility (section 13's MCP
layer) is unchanged.

## Note on CLAUDE.md

`CLAUDE.md`'s illustrative example requests (sections 8 and 32) have been
updated to reference `CLINTRIAL_ETL` / run `2026-10-30-001`, matching the
running system. Everything else in that file (architecture, requirements,
standards) was unchanged.

## Limitations

- Runs locally only; no cloud deployment is configured (by design, per this
  build's scope).
- The `deterministic` LLM provider produces templated, evidence-grounded
  text rather than free-form model reasoning -- sufficient to demonstrate
  the agentic control flow without requiring an API key.
- The knowledge base is 5 short synthetic SOP/runbook documents; retrieval
  quality is illustrative, not a production RAG benchmark.
- "Execution" of a rerun is always simulated (`workflow/graph.py:
  execute_action_node`) -- no real pipeline or database is ever touched.
- `MemorySaver` checkpointing is in-process only; investigations do not
  survive an app restart.
