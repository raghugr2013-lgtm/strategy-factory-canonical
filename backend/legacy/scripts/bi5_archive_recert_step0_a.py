"""BI5 R2 Step-0 (Option A) — re-cert pass over preserved archive.

Walks the existing 15 windows in `bi5_data_certification` and re-runs
`data_engine.bi5_ingest_runner.run_bi5_ingest` against the BI5 archive
on disk (`/app/data/bi5/dukascopy/...`) with the recalibrated scorer
(`tick_validator@P0B-v2`).

Bars and spread are idempotent (matched, never duplicated). Cert
documents are upserted by `(symbol, window_start_utc, window_end_utc)`
so the existing 15 rows are overwritten with new scores in place; no
extra rows are introduced.

Run:  cd /app/backend && python -m scripts.bi5_archive_recert_step0_a
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parents[1] / '.env')

from data_engine.bi5_ingest_runner import run_bi5_ingest  # noqa: E402
from engines.db import get_db  # noqa: E402


async def main():
    db = get_db()
    rows = await db['bi5_data_certification'].find(
        {}, {'_id': 0, 'symbol': 1, 'window_start_utc': 1, 'window_end_utc': 1}
    ).sort([('symbol', 1), ('window_start_utc', 1)]).to_list(length=1000)

    print(f'discovered_existing_windows={len(rows)}', flush=True)

    re_certified = 0
    for r in rows:
        sym = r['symbol']
        s = r['window_start_utc']
        e = r['window_end_utc']
        if s.tzinfo is None:
            s = s.replace(tzinfo=timezone.utc)
        if e.tzinfo is None:
            e = e.replace(tzinfo=timezone.utc)
        # window_end_utc is the *last hour's* timestamp (e.g. 23:00) —
        # we need an exclusive upper bound, so add 1 hour to include it.
        from datetime import timedelta
        e_excl = e + timedelta(hours=1)
        print(f'=== {sym}  {s:%Y-%m-%d %H}h → {e:%Y-%m-%d %H}h '
              f'(exclusive end {e_excl:%Y-%m-%d %H}h)', flush=True)
        t0 = datetime.now(timezone.utc)
        try:
            res = await run_bi5_ingest(sym, start_utc=s, end_utc=e_excl, db=db)
        except Exception as exc:
            print(f'  FAILED: {type(exc).__name__}: {exc}', flush=True)
            continue
        dt = (datetime.now(timezone.utc) - t0).total_seconds()
        print(f'  done in {dt:.1f}s  '
              f'bars_matched={res.get("bars_matched_total")} '
              f'bars_inserted={res.get("bars_inserted_total")} '
              f'spread_upserted={res.get("spread_bars_upserted_total")} '
              f'cert_upserted={res.get("data_cert_upserted")} '
              f'hours_cached={res.get("hours_cached")}/{res.get("hours_total")}',
              flush=True)
        re_certified += int(res.get('data_cert_upserted') or 0)

    print(f'RECERT PASS COMPLETE · cert_upserts_total={re_certified}',
          flush=True)
    # Final distribution dump
    final = await db['bi5_data_certification'].find(
        {}, {'_id': 0, 'symbol': 1, 'verdict': 1, 'bi5_score': 1,
             'window_start_utc': 1, 'window_end_utc': 1, 'subscores': 1,
             'max_silent_gap_s': 1, 'evaluator_version': 1}
    ).sort([('symbol', 1), ('window_start_utc', 1)]).to_list(length=1000)
    pass_n = sum(1 for d in final if d.get('verdict') == 'PASS')
    warn_n = sum(1 for d in final if d.get('verdict') == 'WARN')
    fail_n = sum(1 for d in final if d.get('verdict') == 'FAIL')
    print(f'FINAL DISTRIBUTION · PASS={pass_n} WARN={warn_n} FAIL={fail_n} '
          f'(total={len(final)})', flush=True)
    for d in final:
        s = d.get('subscores') or {}
        ws = d.get('window_start_utc')
        we = d.get('window_end_utc')
        print(
            f'  {d["symbol"]:7s} '
            f'{ws.strftime("%Y-%m-%d") if ws else "?":>10s} → '
            f'{we.strftime("%Y-%m-%d") if we else "?":>10s}  '
            f'score={(d.get("bi5_score") or 0):.4f}  {d.get("verdict"):4s}  '
            f'cov={s.get("cov",0):.2f} integ={s.get("integrity",0):.2f} '
            f'price={s.get("price",0):.2f} dens={s.get("density",0):.3f} '
            f'cont={s.get("continuity",0):.3f}  '
            f'gap={d.get("max_silent_gap_s",0):.0f}s  '
            f'ver={d.get("evaluator_version","?")}',
            flush=True,
        )


asyncio.run(main())
