"""BI5 archive cert/spread pass — operational one-shot (Path A1 Step 1b).

Re-drives data_engine.bi5_ingest_runner.run_bi5_ingest with a DB handle
injected so the validation/certification + spread layers persist
(bars are idempotent: matched, never duplicated). Archive-cached.

Survives pod restarts (lives in the repo, unlike /tmp). Windows below are
the RESUME set after the 2026-06-12 pod recycle; EURUSD Jan-Apr certs +
spread were already persisted before the recycle.

Run:  cd /app/backend && python -m scripts.bi5_archive_cert_pass
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(__file__).resolve().parents[1] / '.env')

from data_engine.bi5_ingest_runner import run_bi5_ingest  # noqa: E402
from engines.db import get_db  # noqa: E402

WINDOWS = [
    ('EURUSD', '2026-05-01', '2026-06-07'),
    ('GBPUSD', '2026-01-01', '2026-03-04'),
    ('GBPUSD', '2026-05-01', '2026-06-01'),
    ('USDJPY', '2026-05-01', '2026-06-01'),
    ('XAUUSD', '2026-05-01', '2026-06-01'),
]

CHUNK_H = 720  # runner cap is 744 hours per call


async def main():
    db = get_db()
    for sym, s, e in WINDOWS:
        start = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(e).replace(tzinfo=timezone.utc)
        cur = start
        while cur < end:
            nxt = min(cur + timedelta(hours=CHUNK_H), end)
            print(f'=== {sym} {cur:%Y-%m-%d %H}h -> {nxt:%Y-%m-%d %H}h', flush=True)
            t0 = datetime.now(timezone.utc)
            r = await run_bi5_ingest(sym, start_utc=cur, end_utc=nxt, db=db)
            dt = (datetime.now(timezone.utc) - t0).total_seconds()
            print(f"  done in {dt:.1f}s -> bars_matched={r.get('bars_matched')} "
                  f"bars_inserted={r.get('bars_inserted')} "
                  f"spread_upserted={r.get('spread_bars_upserted_total')} "
                  f"cert_upserted={r.get('data_cert_upserted')} "
                  f"hours_cached={r.get('hours_cached')}/{r.get('hours_total')}", flush=True)
            cur = nxt
    print('CERT PASS COMPLETE', flush=True)
    async for d in db['bi5_data_certification'].find({}, {'_id': 0, 'symbol': 1, 'verdict': 1, 'bi5_score': 1, 'window_start_utc': 1, 'window_end_utc': 1}):
        print('CERT:', d, flush=True)

asyncio.run(main())
