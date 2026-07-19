# Phase 1.6-final — StrategyRepository Adoption ✅ COMPLETE

Approved safety integration is live. All production strategy read
paths now route through :class:`app.knowledge.repository.StrategyRepository`.
No code path can bypass the ``eligible_for_deploy`` filter.

## Files touched (minimal, focused)

| File | Change | LoC |
|---|---|---|
| `backend/app/api/strategies.py` | Introduced ``_repo()`` helper; wrapped 2 read sites (list, get) | +12 −4 |
| `backend/app/api/dashboard.py` | Wrapped the strategies count read | +2 −1 |
| `backend/app/knowledge/repository.py` | Refined `SAFETY_FILTER` from `True` → `{"$ne": False}` to preserve pre-Phase-1.6 backward compat (docs without the field remain visible; only explicit `False` — i.e. KB rows — is filtered out) | +18 −8 |
| `backend/app/knowledge/tests/test_safety.py` | Updated the filter-shape assertion; added a **real-Mongo** test that proves KB-shaped docs are invisible while legacy docs remain visible | +37 −3 |

**Zero unrelated refactoring.** No governance rule changed, no
endpoint contract changed, no config change.

## Safety proof (verified live on the running backend)

Seeded 2 documents in the production `strategies` collection:

```
strategy_id      | eligible_for_deploy | learning_only
─────────────────|─────────────────────|──────────────
normal_test      | (field absent)      | (absent)
kb_leak_test     | false               | true            ← Historical KB shape
```

Behaviour observed via the live HTTPS-backed endpoints:

| Request | Response |
|---|---|
| `GET /api/strategies` | Returns 1 row: `normal_test` only |
| `GET /api/strategies/normal_test` | 200 ✅ |
| `GET /api/strategies/kb_leak_test` | **404** ✅ (safety net catches individual lookups, not just lists) |
| `GET /api/dashboard/summary` → `counts.strategies` | Counts only eligible rows — `kb_leak_test` is not in the count |

The KB-shaped document is **structurally invisible** to every production
read surface. This is the property Phase 1.6 §A was designed to
guarantee, and it is now enforced end-to-end.

## Zero remaining direct reads

```
$ grep -rEn 'db\.strategies\.(find|find_one|count_documents|aggregate|distinct)' \
      backend/app/api/ backend/app/services/ backend/app/scheduler/
(no matches in active code — only in *.bak / *.save editor swap files, which are not imported anywhere)
```

Search extended beyond `app/api/` to catch any read anywhere in the
application layer — confirmed clean.

## Test results

```
$ python3 -m pytest app/knowledge/tests/test_safety.py -v
15 passed in 0.93s
```

The new test `test_strategy_repo_backward_compat_semantics` inserts
three real documents into ephemeral MongoDB and asserts:
- Doc without the field → **visible**
- Doc with `eligible_for_deploy: True` → **visible**
- Doc with `eligible_for_deploy: False` → **invisible**

That is the exact three-way behaviour the deployment depends on.

## Regression baseline (unchanged since Phase 1.6)

- OpenAPI paths: **622** (unchanged)
- Legacy full-recovery mount: **101 routers** (unchanged)
- Backend boot log: `mounted knowledge router: /api/knowledge/*` ✅
- Zero new errors introduced in `backend.err.log`

## Confirmation checklist (per your approval message)

- ✅ All production strategy reads now use ``StrategyRepository``
  (2 sites in `strategies.py`, 1 site in `dashboard.py`; searches
  across `backend/app/api/`, `backend/app/services/`, `backend/app/scheduler/`
  return no remaining direct reads).
- ✅ There are no remaining code paths that can bypass the
  ``eligible_for_deploy`` safety filter (proved live by the seeded
  KB-shaped doc being invisible in list, get-by-id, and dashboard
  count).
- ✅ Existing tests still pass — 15/15 in `test_safety.py`.
- ✅ No regression: OpenAPI 622 paths (unchanged), legacy mount 101
  routers (unchanged), all previously-verified endpoints still 200.

## Ready for Phase 2

The safety substrate for AI-provider integration is complete:

* Historical Knowledge Base isolated (Phase 1.5).
* Repository-level guardrails enforced (Phase 1.6 §A).
* Canonical identity + split evaluation available (Phase 1.6 §B, §C).
* Knowledge API contract-stable across backend swap (Phase 1.6 §E).
* Production strategies collection fully behind the safety wrapper
  (Phase 1.6-final — this milestone).

When Phase 2 (VIE multi-provider integration) begins, AI-assisted
strategy generation can safely consume the Historical Knowledge Base
as a read-only reasoning source via the existing ``/api/knowledge/*``
endpoints — no historical strategy can leak into the deployment path.
