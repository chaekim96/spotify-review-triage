"""Phase 1: ingest a CSV, verify it, seed the SQLite state store, write reports. No model calls."""

import hashlib
import platform
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, store
from .atomic import atomic_write_json, atomic_write_text
from .vendored import FIELDS, csv_rows, profile as helper_profile, row_sha

# Identity and verified counts of the full course file (from data_raw/manifest.json and the Start phase).
FULL_FILE_SHA256 = "1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6"
FULL_EXPECTED = {
    "records": 660_622,
    "empty_review_text": 13,
    "missing_app_version": 159_701,
    "duplicate_review_ids": 0,
    "distinct_nonempty_texts": 484_189,
}
BATCH = 20_000


class PrepareError(Exception):
    """Raised for any condition that must stop Phase 1 loudly."""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _git_info(repo_root):
    def run(*args):
        try:
            out = subprocess.run(["git", "-C", str(repo_root), *args], capture_output=True, text=True, timeout=10)
            return out.stdout.strip() if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    commit = run("rev-parse", "HEAD")
    dirty = run("status", "--porcelain")
    return {"commit": commit, "dirty": bool(dirty) if dirty is not None else None}


def _insert(conn, batch):
    conn.executemany(
        "INSERT INTO records(review_id, seq, source_sha256, text_sha256, status, reason, attempts, updated_at) "
        "VALUES(?,?,?,?,?,?,0,?)",
        batch,
    )


def prepare(csv_path, run_dir, expect_full=False, grading_dir=None, repo_root=None):
    csv_path = Path(csv_path).resolve()
    run_dir = Path(run_dir)
    repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[1]
    if not csv_path.is_file():
        raise PrepareError(f"CSV not found: {csv_path}")
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. Helper profile (verbatim, authoritative for file hash and parsed-rows hash).
    prof = helper_profile(csv_path)
    is_full = prof["file_sha256"] == FULL_FILE_SHA256
    if expect_full and not is_full:
        raise PrepareError(f"--expect-full but file sha256 {prof['file_sha256']} != {FULL_FILE_SHA256}")
    assert_counts = expect_full or is_full

    conn = store.connect(run_dir / "state.sqlite")
    try:
        prev_input = store.get_meta(conn, "input_file_sha256")
        if prev_input and prev_input != prof["file_sha256"]:
            raise PrepareError(
                f"run dir {run_dir} was seeded from a different input (sha256 {prev_input}); "
                "use a new --run-dir for a different CSV."
            )
        existing = dict(conn.execute("SELECT review_id, source_sha256 FROM records"))

        # 2. Own streaming pass: per-row source hash, text stats, state rows.
        seen = set()
        text_counts = Counter()
        content = hashlib.sha256()
        counts = Counter()
        quarantine = []
        conflicts = []
        batch = []
        now = _now()
        for seq, row in enumerate(csv_rows(csv_path)):
            rid = row["review_id"]
            if not rid:
                raise PrepareError(f"row {seq}: blank review_id")
            digest = row_sha(row)
            content.update(bytes.fromhex(digest))
            counts["records"] += 1
            empty = not row["review_text"].strip()
            counts["empty_review_text"] += empty
            counts["literal_empty_text"] += row["review_text"] == ""
            counts["missing_app_version"] += not row["app_version"].strip()
            if rid in seen:
                counts["duplicate_review_ids"] += 1
                continue
            seen.add(rid)
            tsha = hashlib.sha256(row["review_text"].encode("utf-8")).hexdigest()
            if empty:
                quarantine.append({"review_id": rid, "reason": "empty_review_text"})
            else:
                text_counts[tsha] += 1
            if rid in existing:
                if existing[rid] != digest:
                    conflicts.append(rid)
                continue
            batch.append((rid, seq, digest, tsha, "quarantined" if empty else "pending",
                          "empty_review_text" if empty else None, now))
            if len(batch) >= BATCH:
                _insert(conn, batch)
                batch = []
        if batch:
            _insert(conn, batch)

        if conflicts:
            raise PrepareError(
                f"{len(conflicts)} review_ids already in the state store have a different source_sha256 "
                f"(first: {conflicts[:3]}). The input changed; refusing to continue."
            )

        # 3. Cross-checks against the helper, then expected counts.
        if content.hexdigest() != prof["parsed_rows_sha256"]:
            raise PrepareError("parsed_rows_sha256 differs between spp pass and vendored helper")
        for key in ("records", "duplicate_review_ids", "empty_review_text", "missing_app_version"):
            if counts[key] != prof["counts"][key]:
                raise PrepareError(f"{key}: spp counted {counts[key]}, vendored helper counted {prof['counts'][key]}")

        distinct = len(text_counts)
        nonempty_rows = sum(text_counts.values())  # nonempty rows with a first-seen review_id
        repeated = {k: v for k, v in text_counts.items() if v > 1}
        verified = {
            "records": counts["records"],
            "empty_review_text": counts["empty_review_text"],
            "missing_app_version": counts["missing_app_version"],
            "duplicate_review_ids": counts["duplicate_review_ids"],
            "distinct_nonempty_texts": distinct,
        }
        expectation = {"asserted": bool(assert_counts), "expected": FULL_EXPECTED if assert_counts else None, "ok": None}
        if assert_counts:
            bad = {k: {"expected": FULL_EXPECTED[k], "got": verified[k]} for k in FULL_EXPECTED if verified[k] != FULL_EXPECTED[k]}
            expectation["ok"] = not bad
            if bad:
                raise PrepareError(f"full-file count assertion FAILED: {bad}")

        store.set_meta(conn, "input_file_sha256", prof["file_sha256"])
        store.set_meta(conn, "input_path", str(csv_path))
        store.set_meta(conn, "tool_version", __version__)
        conn.commit()
    except BaseException:
        conn.rollback()
        conn.close()
        raise

    # 4. Reports (written only after the DB commit succeeded).
    status = store.status_counts(conn)
    pending_ids = [r[0] for r in conn.execute("SELECT review_id FROM records WHERE status='pending' ORDER BY seq")]
    conn.close()

    # pending_ids.txt is regenerated from the DB, so after a partial run it lists only what is still pending.
    atomic_write_text(run_dir / "pending_ids.txt", "".join(i + "\n" for i in pending_ids))

    git = _git_info(repo_root)
    manifest = {
        "input_path": str(csv_path),
        "input_file_sha256": prof["file_sha256"],
        "input_size_bytes": csv_path.stat().st_size,
        "row_count": counts["records"],
        "is_full_course_file": is_full,
        "code_git_commit": git["commit"],
        "code_git_dirty": git["dirty"],
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "created_utc": _now(),
        "tool_version": __version__,
        "state_db": "state.sqlite",
        "pending_queue": "pending_ids.txt",
    }
    atomic_write_json(run_dir / "data_manifest.json", manifest)

    report = {
        "helper_profile": prof,
        "verified_counts": verified,
        "expectation": expectation,
        "literal_empty_texts": counts["literal_empty_text"],
        "text_repeat_stats": {
            "nonempty_rows": nonempty_rows,
            "distinct_nonempty_texts": distinct,
            "rows_reusable_via_exact_text_cache": nonempty_rows - distinct,
            "texts_occurring_more_than_once": len(repeated),
            "rows_in_repeated_texts": sum(repeated.values()),
            "max_repeat_count": max(text_counts.values(), default=0),
            "top_repeat_counts": sorted(text_counts.values(), reverse=True)[:10],
        },
        "state_after_seed": {"statuses": status, "pending_queue_length": len(pending_ids)},
        "quarantine": quarantine,
        "fields": list(FIELDS),
    }
    atomic_write_json(run_dir / "ingestion_report.json", report)

    grading_path = None
    if is_full and grading_dir is not None:
        grading_path = Path(grading_dir) / "ingestion.json"
        atomic_write_json(grading_path, prof)
    return {"manifest": manifest, "report": report, "grading_ingestion": str(grading_path) if grading_path else None}
