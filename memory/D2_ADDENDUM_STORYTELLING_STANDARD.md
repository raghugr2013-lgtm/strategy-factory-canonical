# D2 Addendum — Storytelling Copy Standard (permanent)

> Refinement approved 2026-07-20. Applies to D2 and carries forward to D3 → D8 wherever activity history appears.

## 1. Principle

Events should read as **the diary of an autonomous AI organization**, not as system logs.

The Timeline is prose, not telemetry. The operator, researcher, and executive should each read the same sentence and understand it in one pass. Technical fields (confidence, method, provenance) live behind the **Advanced Lens** (D1 §11) — never in the primary sentence.

## 2. Copy shape

```
[Actor Division]  [action verb — past tense]  [subject]  [after clause · optional]
```

Examples:
- "Research Division generated a new EURUSD breakout candidate."
- "Knowledge Base promoted EURUSD Breakout v3 after successful validation."
- "Learning Division recalibrated confidence using 248 new observations."
- "Portfolio Division added GBPUSD Trend v2 to the shortlist."
- "Governance flagged EURUSD Breakout v3 for operator review."
- "Execution observed p95 fill quality of 1.2 pips on 30 EURUSD trades."
- "Maintenance completed a BI5 sweep with zero gaps."

## 3. Rules

1. **Actor is a Division** — always. `Research Division`, `Knowledge Base`, `Learning Division`, `Portfolio Division`, `Governance`, `Execution`, `Maintenance`, `Master Bot`. Never `worker-01`, `orchestrator.py`, `service.knowledge`.
2. **Verbs are past tense, single word where possible** — `generated`, `promoted`, `validated`, `recalibrated`, `flagged`, `observed`, `completed`, `queued`.
3. **Subjects are named** — never `strategy_id 47d3...`. Always `EURUSD Breakout v3`, `challenge FTMO-100k`, `arxiv paper on regime detection`.
4. **After-clauses add narrative context** — `after successful validation`, `using 248 new observations`, `on the last 30 days`.
5. **Numbers when meaningful, not always** — a count belongs in the sentence when it makes the story concrete (`248 observations`, `30 trades`). Otherwise, defer to Advanced Lens.
6. **No jargon on Layer 1** — no `p95`, no `walk-forward`, no `dedup_threshold`, no `event_id`. Those chips appear only under Advanced Lens.
7. **One sentence, ≤ 90 characters** — the detail line is optional and may hold one more clause (`confidence rose from 0.61 to 0.87`).
8. **Present the *why* in the detail line when it aids the story** — `after regime shift detected on 2026-07-19`.

## 4. Actor-to-Division mapping (rewrite of D2 §4)

| # | Actor code (internal) | Public Division name | Icon |
|---|---|---|---|
| 1 | research | **Research Division** | search |
| 2 | generation | **Research Division** (same division · verb differentiates) | sparkles |
| 3 | backtest | **Validation Division** | bar-chart-2 |
| 4 | mutation | **Mutation Division** | git-branch |
| 5 | knowledge | **Knowledge Base** | book |
| 6 | learning | **Learning Division** | activity |
| 7 | portfolio | **Portfolio Division** | layers |
| 8 | execution | **Execution Division** | terminal |
| 9 | maintenance | **Maintenance** | wrench |
| 10 | approval | **Master Bot** (requests approval on behalf of a division) | flag |

Advanced Lens exposes the *worker-level* attribution (`worker-01 · research`) as a small chip below the sentence — but the sentence itself always uses the Division voice.

## 5. Copy library governance

- **D7 owns the full 40+ headline library** — one per common event pattern per Division.
- Every new event type introduced backend-side must produce a headline template *before* it ships to the Timeline.
- The Copilot uses the same library — its "explain this" answers are grounded in the same voice.

## 6. Application to D3 → D8

- **D3 Approval Center** — approval headlines follow the same shape: `Master Bot requests approval for EURUSD Breakout v3 promotion.`
- **D4 Workforce Org Chart** — worker cards show the Division name prominently; internal worker id is Advanced-only.
- **D5 Signature Graphics** — every tooltip and label uses Division voice.
- **D7 Empty state library** — copy specimens rewritten to Division voice.

## 7. Anti-patterns (never do)

- ❌ `orchestrator.py:242 opened LLM call provider=openai model=gpt-5`
- ❌ `event_id: 47d3f... completed at 12:24:14.041`
- ❌ `worker-01 finished task`
- ❌ `Retrieval returned 6 results with 0.87 confidence` *(reveals machinery)*
- ✅ `Research Division retrieved 6 relevant papers on regime detection.`

---

*Storytelling Copy Standard adopted. Carried forward to D3–D8 permanently.*
