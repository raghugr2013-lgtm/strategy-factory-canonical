"""Master Bot V1 — .cbotpack Builder (MB-8).

Goal:
    Bundle a Master Bot export (.cs + metadata sidecar) into a single
    drop-in archive an operator can hand to cTrader's cAlgo IDE or to a
    future automated deployment pipeline.

Archive layout (`.cbotpack` is a renamed `.zip`):

    MasterBot_<name>_rev<N>_<short>.cbotpack
    ├── MainSource.cs                       ← exported cAlgo Robot
    ├── Properties.xml                      ← cAlgo-style manifest
    ├── definition.json                     ← full immutable definition payload
    ├── manifest.json                       ← pack-level metadata (sha256, ids)
    ├── ranker_weights.json                 ← snapshot at export time
    ├── members.csv                         ← human-readable tier roster
    └── README.md                           ← operator-facing instructions

The pack ALWAYS contains exactly the files above. Any future asset
(e.g. compiled .dll once we transpile per-strategy IR) is added via a
new optional file, never by renaming/removing an existing one.

What MB-8 does NOT do (deferred):
    * Compile the .cs to .dll (needs `dotnet` toolchain — future MB-9).
    * Sign the pack (no PKI available on the dev pod).
    * Deploy to cTrader-CLI (MB-9).
    * Upload to a registry (MB-10).
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import logging
import os
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from engines.db import get_db
from engines import master_bot_definition as mbd
from engines import master_bot_export as mbx

logger = logging.getLogger(__name__)

PACKS_COLL          = "master_bot_packs"
PACK_BUILDER_VERSION = "v1.0"
PACK_DIR_DEFAULT     = os.environ.get(
    "MASTER_BOT_PACK_DIR", "/app/data_imports/master_bot_packs"
)


# ── Time helper ──────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ensure_indexes() -> None:
    db = get_db()
    try:
        await db[PACKS_COLL].create_index("pack_id", unique=True)
        await db[PACKS_COLL].create_index(
            [("master_bot_id", 1), ("created_at", -1)],
        )
        await db[PACKS_COLL].create_index("revision_id")
        await db[PACKS_COLL].create_index("export_id")
    except Exception:                                          # pragma: no cover
        logger.exception("master_bot_pack: ensure_indexes failed")


def _pack_dir() -> str:
    out = os.environ.get("MASTER_BOT_PACK_DIR") or PACK_DIR_DEFAULT
    os.makedirs(out, exist_ok=True)
    return out


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


# ── Manifest emitters ───────────────────────────────────────────────

def _emit_properties_xml(payload: Dict[str, Any], *, csharp_class: str,
                         revision_id: str, definition_hash: str) -> str:
    """Minimal cAlgo-style Properties.xml.

    NOTE: cTrader's exact .algo format is undocumented for third-party
    re-builds. This Properties.xml is a best-effort approximation that
    operators (and future MB-9 cTrader-CLI integration) can extend in
    place. The fields below match what the cAlgo IDE shows in the
    "Properties" panel of an imported cBot.
    """
    bot = payload.get("master_bot") or {}
    runtime = payload.get("runtime") or {}

    def safe(s: Any) -> str:
        return (
            str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<cBot xmlns="https://ctrader.com/cAlgo/Properties">\n'
        f'  <Name>{safe(bot.get("name"))}</Name>\n'
        f'  <Description>{safe(bot.get("description") or "AI Strategy Factory Master Bot")}</Description>\n'
        f'  <Author>{safe(bot.get("owner") or "AI Strategy Factory")}</Author>\n'
        f'  <Version>1.0.{int((revision_id or "0")[:8] or "0", 16) % 9000 + 1000}</Version>\n'
        f'  <Class>{safe(csharp_class)}</Class>\n'
        f'  <MasterBotId>{safe(bot.get("id"))}</MasterBotId>\n'
        f'  <RevisionId>{safe(revision_id)}</RevisionId>\n'
        f'  <DefinitionHash>{safe(definition_hash)}</DefinitionHash>\n'
        f'  <RuntimeMode>{safe(runtime.get("mode") or "multi_strategy")}</RuntimeMode>\n'
        '  <Tags>\n'
        '    <Tag>master-bot</Tag>\n'
        f'    <Tag>{safe(runtime.get("mode") or "multi_strategy")}</Tag>\n'
        '  </Tags>\n'
        '</cBot>\n'
    )


def _emit_members_csv(payload: Dict[str, Any]) -> str:
    """Operator-facing roster. UTF-8 CSV."""
    lines = ["tier,order,enabled,strategy_hash,pair,timeframe,style,profit_factor,win_rate,pass_probability,deploy_score,candidate_score,lifecycle_stage"]
    for tier in payload.get("tiers") or []:
        tk = tier.get("tier_key")
        for m in tier.get("members") or []:
            snap = m.get("snapshot") or {}
            row = [
                tk or "",
                str(m.get("order_index") or 0),
                "true" if m.get("enabled") else "false",
                m.get("strategy_hash") or "",
                snap.get("pair") or "",
                snap.get("timeframe") or "",
                snap.get("style") or "",
                str(snap.get("profit_factor") if snap.get("profit_factor") is not None else ""),
                str(snap.get("win_rate") if snap.get("win_rate") is not None else ""),
                str(snap.get("pass_probability") if snap.get("pass_probability") is not None else ""),
                str(snap.get("deploy_score") if snap.get("deploy_score") is not None else ""),
                str(snap.get("candidate_score") if snap.get("candidate_score") is not None else ""),
                snap.get("lifecycle_stage") or "",
            ]
            lines.append(",".join(row))
    return "\n".join(lines) + "\n"


def _emit_readme(payload: Dict[str, Any], *, manifest: Dict[str, Any]) -> str:
    bot = payload.get("master_bot") or {}
    runtime = payload.get("runtime") or {}
    ranker = payload.get("ranker") or {}
    counts: Dict[str, int] = {"tier1": 0, "tier2": 0, "tier3": 0}
    enabled = 0
    for tier in payload.get("tiers") or []:
        tk = tier.get("tier_key")
        members = tier.get("members") or []
        if tk in counts:
            counts[tk] = len(members)
        enabled += sum(1 for m in members if m.get("enabled"))
    total = sum(counts.values())
    weights = ranker.get("weights") or {}
    weight_lines = "\n".join(
        f"- `{k}` = {v}" for k, v in sorted(weights.items())
    )
    return f"""# {bot.get('name') or 'Master Bot'} — .cbotpack

| Field             | Value                                       |
| ----------------- | ------------------------------------------- |
| Master Bot ID     | `{bot.get('id') or ''}`                     |
| Revision ID       | `{manifest.get('revision_id') or ''}`       |
| Revision Number   | rev {manifest.get('rev')}                   |
| Definition Hash   | `{manifest.get('definition_hash') or ''}`    |
| Runtime Mode      | `{runtime.get('mode') or 'multi_strategy'}` |
| Tier 1 / 2 / 3    | {counts['tier1']} / {counts['tier2']} / {counts['tier3']} |
| Enabled / Total   | {enabled} / {total}                          |
| Exported At       | {manifest.get('exported_at') or ''}          |
| Packed At         | {manifest.get('packed_at') or ''}            |
| Pack Builder      | {manifest.get('pack_builder_version') or ''} |

## Ranker context (frozen at compile time)

Version: `{ranker.get('version') or 'v1.0'}`

{weight_lines or '- (no weights recorded)'}

## How to load in cTrader

1. Extract this `.cbotpack` (it is a renamed `.zip`).
2. Open cTrader → cAlgo → cBots → **+ New cBot from Code**.
3. Paste `MainSource.cs` content into the new cBot.
4. Hit **Build**. If your account has access to the cAlgo Robot API,
   the build should succeed without modification.
5. Attach the cBot to the desired chart(s) and **Run**.

> NOTE — `Tier{{1,2,3}}Strategy_*` classes are deterministic refusal
> stubs in this revision. They do NOT open orders. Replace each
> stub's `Step()` body with the IR-transpiled implementation produced
> by `POST /api/generate-cbot` (existing per-strategy export flow) to
> activate live trading.

## Files in this pack

| File                  | Purpose                                          |
| --------------------- | ------------------------------------------------ |
| `MainSource.cs`       | cAlgo Robot source — Master Bot shell + tier classes |
| `Properties.xml`      | cAlgo manifest (Name, Author, Version, RuntimeMode) |
| `definition.json`     | Full immutable definition payload (canonical, hash-stable) |
| `manifest.json`       | Pack-level metadata (sha256 over each file, ids) |
| `ranker_weights.json` | Ranker version + weights at compile time         |
| `members.csv`         | Human-readable roster                             |
| `README.md`           | This file                                         |

This pack is byte-stable across re-builds of the same `revision_id`
**except** the `packed_at` and `exported_at` timestamps. Future MB-8.1
will add a `--deterministic` mode that zero-clocks those for parity
diffing.

## Audit

Every pack ID is logged in MongoDB `master_bot_packs`. The Master Bot
Definition's `payload.export_targets.cbotpack` slot is also stamped
with this pack's path + sha256 so the definition row is a one-stop
audit point.

---

*Generated by AI Strategy Factory · Master Bot V1 · MB-8 Pack Builder.*
"""


# ── Public: build pack ──────────────────────────────────────────────

async def build_pack(
    master_bot_id: str,
    *,
    export_id: Optional[str] = None,
    revision_id: Optional[str] = None,
    actor: str = "admin",
) -> Dict[str, Any]:
    """Build a `.cbotpack` archive.

    Resolution order:
      1. `export_id` (most explicit — uses that exact .cs + sidecar).
      2. `revision_id` (auto-exports if no prior export exists).
      3. Neither → latest export, or latest revision, or fresh compile.
    """
    await ensure_indexes()
    db = get_db()

    # Resolve the export to wrap.
    export_row: Optional[Dict[str, Any]] = None
    if export_id:
        export_row = await db[mbx.EXPORTS_COLL].find_one(
            {"export_id": export_id}, {"_id": 0}
        )
        if not export_row:
            raise ValueError("export not found")
        if export_row.get("master_bot_id") != master_bot_id:
            raise ValueError("export does not belong to this master bot")
    elif revision_id:
        # Find latest export for this revision; else export fresh.
        export_row = await db[mbx.EXPORTS_COLL].find_one(
            {"revision_id": revision_id, "master_bot_id": master_bot_id},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        if not export_row:
            export_row = await mbx.export_master_bot(
                master_bot_id, revision_id=revision_id, actor=actor,
            )
    else:
        # Latest export for this bot; else export fresh from latest rev.
        export_row = await db[mbx.EXPORTS_COLL].find_one(
            {"master_bot_id": master_bot_id},
            {"_id": 0},
            sort=[("created_at", -1)],
        )
        if not export_row:
            export_row = await mbx.export_master_bot(
                master_bot_id, actor=actor,
            )

    rev_id = export_row.get("revision_id")
    revision = await mbd.get_definition(revision_id=rev_id)
    if not revision:
        raise ValueError("backing definition not found")
    payload = revision.get("payload") or {}

    # Read the .cs back from disk (authoritative — we never re-render
    # here; the pack must reflect the exact export sha256).
    cs_path = export_row.get("cs_path")
    if not cs_path or not os.path.exists(cs_path):
        raise ValueError("backing .cs artifact missing on disk")
    with open(cs_path, "rb") as f:
        cs_bytes = f.read()

    # Compose pack contents.
    ranker_weights = (payload.get("ranker") or {}).get("weights") or {}
    ranker_blob = json.dumps(
        {"version": (payload.get("ranker") or {}).get("version") or "v1.0",
         "weights": ranker_weights},
        sort_keys=True, indent=2,
    ).encode("utf-8")

    # ── definition.json: strip transient export_targets so subsequent
    # packs of the same export produce byte-stable definition.json.
    # `export_targets.{cs_text,cbotpack,wasm}` are stamped POST-export
    # / POST-pack and would otherwise leak prior-run metadata into the
    # next pack. The canonical definition payload (what the hash was
    # computed over) deliberately had `export_targets: { all-null }`.
    clean_payload = copy.deepcopy(payload)
    clean_payload["export_targets"] = {
        "cs_text":  None,
        "cbotpack": None,
        "wasm":     None,
    }
    definition_blob = json.dumps(clean_payload, sort_keys=True, indent=2).encode("utf-8")
    members_csv_blob = _emit_members_csv(payload).encode("utf-8")
    properties_blob = _emit_properties_xml(
        payload,
        csharp_class=export_row.get("csharp_class") or "MasterBotShell",
        revision_id=rev_id or "",
        definition_hash=revision.get("definition_hash") or "",
    ).encode("utf-8")

    # Tentative manifest (sha256 of each file). README references manifest
    # so we compute manifest BEFORE rendering README.
    pack_id = uuid.uuid4().hex
    packed_at = _now_iso()
    manifest = {
        "pack_id":         pack_id,
        "master_bot_id":   master_bot_id,
        "revision_id":     rev_id,
        "rev":             revision.get("rev"),
        "export_id":       export_row.get("export_id"),
        "definition_hash": revision.get("definition_hash"),
        "exported_at":     export_row.get("created_at"),
        "packed_at":       packed_at,
        "pack_builder_version": PACK_BUILDER_VERSION,
        "exporter_version": export_row.get("exporter_version"),
        "csharp_class":    export_row.get("csharp_class"),
        "files": {
            "MainSource.cs":       {"size": len(cs_bytes),         "sha256": _sha256_bytes(cs_bytes)},
            "Properties.xml":      {"size": len(properties_blob),  "sha256": _sha256_bytes(properties_blob)},
            "definition.json":     {"size": len(definition_blob),  "sha256": _sha256_bytes(definition_blob)},
            "ranker_weights.json": {"size": len(ranker_blob),      "sha256": _sha256_bytes(ranker_blob)},
            "members.csv":         {"size": len(members_csv_blob), "sha256": _sha256_bytes(members_csv_blob)},
            # README sha is filled below (depends on the manifest itself).
        },
    }
    readme_blob = _emit_readme(payload, manifest=manifest).encode("utf-8")
    manifest["files"]["README.md"] = {
        "size": len(readme_blob), "sha256": _sha256_bytes(readme_blob),
    }
    manifest_blob = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")
    # Manifest file itself is included as a separate entry without
    # self-referencing its own hash (avoids the recursive-hash trap).

    # Build the zip in memory then flush to disk.
    bot_name = (payload.get("master_bot") or {}).get("name") or "MasterBot"
    safe_name = "".join(c for c in bot_name if c.isalnum()) or "MasterBot"
    short_hash = (revision.get("definition_hash") or "sha256:00000000").split(":")[-1][:8]
    pack_filename = f"{safe_name}_rev{revision.get('rev')}_{short_hash}.cbotpack"

    out_path = os.path.join(_pack_dir(), pack_filename)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("MainSource.cs",       cs_bytes)
        zf.writestr("Properties.xml",      properties_blob)
        zf.writestr("definition.json",     definition_blob)
        zf.writestr("ranker_weights.json", ranker_blob)
        zf.writestr("members.csv",         members_csv_blob)
        zf.writestr("README.md",           readme_blob)
        zf.writestr("manifest.json",       manifest_blob)
    zip_bytes = buf.getvalue()
    with open(out_path, "wb") as f:
        f.write(zip_bytes)

    pack_sha = _sha256_bytes(zip_bytes)

    pack_row = {
        "pack_id":         pack_id,
        "master_bot_id":   master_bot_id,
        "revision_id":     rev_id,
        "rev":             revision.get("rev"),
        "export_id":       export_row.get("export_id"),
        "pack_path":       out_path,
        "filename":        pack_filename,
        "sha256":          pack_sha,
        "size_bytes":      len(zip_bytes),
        "pack_builder_version": PACK_BUILDER_VERSION,
        "csharp_class":    export_row.get("csharp_class"),
        "built_by":        actor,
        "created_at":      packed_at,
        "files":           manifest["files"],
    }
    await db[PACKS_COLL].insert_one(pack_row)

    # Stamp the definition's cbotpack target slot.
    try:
        await mbd.record_export_target(
            rev_id,
            "cbotpack",
            {
                "pack_id":   pack_id,
                "pack_path": out_path,
                "sha256":    pack_sha,
                "filename":  pack_filename,
                "packed_at": packed_at,
            },
        )
    except Exception:                                          # pragma: no cover
        logger.exception("master_bot_pack: record_export_target failed")

    return {k: v for k, v in pack_row.items() if k != "_id"}


async def list_packs(
    master_bot_id: str, *, limit: int = 50,
) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db[PACKS_COLL].find(
        {"master_bot_id": master_bot_id}, {"_id": 0}
    ).sort("created_at", -1).limit(int(limit))
    return [d async for d in cur]


async def read_pack(pack_id: str) -> Tuple[str, bytes]:
    db = get_db()
    row = await db[PACKS_COLL].find_one(
        {"pack_id": pack_id}, {"_id": 0}
    )
    if not row:
        raise ValueError("pack not found")
    path = row.get("pack_path")
    if not path or not os.path.exists(path):
        raise ValueError("pack artifact missing on disk")
    with open(path, "rb") as f:
        return row.get("filename"), f.read()
