"""BI5 R2 Step-0 (Option A) — FAST re-cert pass.

Same purpose as `bi5_archive_recert_step0_a.py` but bypasses the bars
+ spread persistence layers (which were the slow path: ~43k spread
upserts per 720-hour window). We:

  1. Read the same `bi5_data_certification` windows that exist today.
  2. For each window, walk hour-by-hour over the on-disk BI5 archive,
     decode ticks, call `validate_hour` (now with the v2 600 s empty-
     hour fallback), and collect HourValidation objects.
  3. Call `aggregate_window` (now with the v2 95th-percentile
     continuity rollup + recalibrated PASS/WARN thresholds + new FX
     density floors) to produce a `BI5ScoreReport`.
  4. Upsert via the same persistence adapter (`upsert_data_certification`).

Pure functions. No bars touched. No spread touched. No tick-data row
inserted. Existing 15 cert documents are replaced in place via the
same unique key `(symbol, window_start_utc, window_end_utc)`.

Run:  cd /app/backend && python -m scripts.bi5_archive_recert_step0_a_fast
"""
import asyncio
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parents[1] / '.env')

from engines.db import get_db  # noqa: E402
from engines.tick_validator import (  # noqa: E402
    DEFAULT_WEIGHTS,
    aggregate_window,
    validate_hour,
    EVALUATOR_VERSION,
)
from engines.persistence_adapters.bi5_data_certification_store import (  # noqa: E402
    upsert_data_certification,
)
from data_engine.tick_aggregator import decode_bi5_hour  # noqa: E402
from config.bi5_symbols import get_bi5_symbol_spec  # noqa: E402
from data_engine.tick_archive import BI5TickArchive  # noqa: E402
from data_engine.market_calendar import is_bi5_session_active  # noqa: E402


SOURCE_ID = 'dukascopy'


def _decode_and_validate_hour(arc: BI5TickArchive, symbol: str,
                              hour_utc: datetime):
    spec = get_bi5_symbol_spec(symbol)
    spec_mt = spec.market_type
    hour_is_open = is_bi5_session_active(hour_utc, spec_mt)

    if not arc.has(symbol, hour_utc, SOURCE_ID):
        # missing-from-cache: classify by calendar
        status = 'missing' if hour_is_open else 'expected_empty'
        return validate_hour(None, hour_utc=hour_utc, symbol=symbol,
                             status=status)
    try:
        payload = arc.read(symbol, hour_utc, SOURCE_ID)
        ticks = decode_bi5_hour(payload, hour_utc=hour_utc, spec=spec)
    except Exception:
        # decode_fail / corrupt payload
        return validate_hour(None, hour_utc=hour_utc, symbol=symbol,
                             status='decode_fail')

    if hour_is_open:
        return validate_hour(ticks, hour_utc=hour_utc, symbol=symbol,
                             status='ok')
    else:
        return validate_hour(None, hour_utc=hour_utc, symbol=symbol,
                             status='expected_empty')


async def main():
    print(f'evaluator_version_in_use={EVALUATOR_VERSION}', flush=True)
    db = get_db()
    rows = await db['bi5_data_certification'].find(
        {}, {'_id': 0, 'symbol': 1,
             'window_start_utc': 1, 'window_end_utc': 1}
    ).sort([('symbol', 1), ('window_start_utc', 1)]).to_list(length=1000)
    print(f'discovered_existing_windows={len(rows)}', flush=True)

    arc = BI5TickArchive()

    for r in rows:
        sym = r['symbol']
        s = r['window_start_utc']
        e = r['window_end_utc']
        if s.tzinfo is None:
            s = s.replace(tzinfo=timezone.utc)
        if e.tzinfo is None:
            e = e.replace(tzinfo=timezone.utc)
        e_excl = e + timedelta(hours=1)
        t0 = datetime.now(timezone.utc)

        validations = []
        n_hours = int((e_excl - s).total_seconds() // 3600)
        for i in range(n_hours):
            hv = _decode_and_validate_hour(arc, sym, s + timedelta(hours=i))
            validations.append(hv)

        if not validations:
            print(f'{sym} {s:%Y-%m-%d} -> {e:%Y-%m-%d} SKIPPED (no hours)',
                  flush=True)
            continue

        report = aggregate_window(validations, weights=DEFAULT_WEIGHTS)
        cert_res = await upsert_data_certification(db, report)
        dt = (datetime.now(timezone.utc) - t0).total_seconds()
        print(
            f'{sym} {s:%Y-%m-%d}→{e:%Y-%m-%d}  hours={n_hours} '
            f'score={report.bi5_score:.4f}  {report.verdict:4s}  '
            f'cov={report.subscores["cov"]:.2f} '
            f'integ={report.subscores["integrity"]:.2f} '
            f'price={report.subscores["price"]:.2f} '
            f'dens={report.subscores["density"]:.3f} '
            f'cont={report.subscores["continuity"]:.3f}  '
            f'gap={report.max_silent_gap_s:.0f}s  '
            f'mods={cert_res.get("modified")}/'
            f'ups={cert_res.get("upserted")}  '
            f'({dt:.1f}s)',
            flush=True,
        )

    final = await db['bi5_data_certification'].find(
        {}, {'_id': 0, 'symbol': 1, 'verdict': 1, 'bi5_score': 1,
             'window_start_utc': 1, 'window_end_utc': 1, 'subscores': 1,
             'max_silent_gap_s': 1, 'evaluator_version': 1, 'ticks_total': 1,
             'hours_present': 1, 'hours_expected_empty': 1,
             'hours_missing': 1, 'hours_decode_fail': 1,
             'sparse_hours': 1, 'low_density_hours': 1}
    ).sort([('symbol', 1), ('window_start_utc', 1)]).to_list(length=1000)
    pass_n = sum(1 for d in final if d.get('verdict') == 'PASS')
    warn_n = sum(1 for d in final if d.get('verdict') == 'WARN')
    fail_n = sum(1 for d in final if d.get('verdict') == 'FAIL')
    print('---FINAL DISTRIBUTION---', flush=True)
    print(f'TOTAL={len(final)}  PASS={pass_n}  WARN={warn_n}  '
          f'FAIL={fail_n}', flush=True)
    for d in final:
        s = d.get('subscores') or {}
        ws = d.get('window_start_utc')
        we = d.get('window_end_utc')
        print(
            f'  {d["symbol"]:7s} '
            f'{ws.strftime("%Y-%m-%d") if ws else "?":>10s} → '
            f'{we.strftime("%Y-%m-%d") if we else "?":>10s}  '
            f'score={(d.get("bi5_score") or 0):.4f}  '
            f'{d.get("verdict"):4s}  '
            f'cov={s.get("cov",0):.2f} integ={s.get("integrity",0):.2f} '
            f'price={s.get("price",0):.2f} dens={s.get("density",0):.3f} '
            f'cont={s.get("continuity",0):.3f}  '
            f'ticks={d.get("ticks_total",0)}  '
            f'present={d.get("hours_present",0)} '
            f'empty={d.get("hours_expected_empty",0)} '
            f'miss={d.get("hours_missing",0)} '
            f'dec_fail={d.get("hours_decode_fail",0)}  '
            f'gap={d.get("max_silent_gap_s",0):.0f}s  '
            f'ver={d.get("evaluator_version","?")}',
            flush=True,
        )


asyncio.run(main())
