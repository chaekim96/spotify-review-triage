"""Offline tests for Phase 1. Small fixtures only; the real dataset is never read."""

import csv
import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

from spp import atomic, vendored
from spp.prepare import PrepareError, prepare
from spp.vendored import FIELDS, checker, row_sha

FIXTURE = Path(__file__).parent / "fixtures" / "small.csv"
HEADER = list(FIELDS)


def run(csv_path, run_dir, **kw):
    return prepare(csv_path, run_dir, repo_root=run_dir, **kw)


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(HEADER)
        w.writerows(rows)


def db(run_dir):
    c = sqlite3.connect(run_dir / "state.sqlite")
    c.row_factory = sqlite3.Row
    return c


def test_vendored_checker_is_verbatim():
    import hashlib

    assert hashlib.sha256(vendored.VENDOR_PATH.read_bytes()).hexdigest() == vendored.VENDOR_SHA256


def test_row_sha_matches_contract_and_helper(tmp_path):
    rows = list(checker.csv_rows(FIXTURE))
    import hashlib

    for row in rows:
        expected = hashlib.sha256(
            json.dumps([row[k] for k in FIELDS], ensure_ascii=False, separators=(",", ":"), sort_keys=True, allow_nan=False).encode("utf-8")
        ).hexdigest()
        assert row_sha(row) == expected
    out = run(FIXTURE, tmp_path / "r")
    stored = {r["review_id"]: r["source_sha256"] for r in db(tmp_path / "r").execute("SELECT * FROM records")}
    assert stored == {row["review_id"]: row_sha(row) for row in rows}


def test_multiline_field_parsed_as_one_row(tmp_path):
    out = run(FIXTURE, tmp_path / "r")
    assert FIXTURE.read_text(encoding="utf-8").count("\n") == 8  # 7 CSV lines + 1 embedded newline
    assert out["manifest"]["row_count"] == 6
    assert db(tmp_path / "r").execute("SELECT COUNT(*) FROM records").fetchone()[0] == 6


def test_empty_text_is_quarantined(tmp_path):
    out = run(FIXTURE, tmp_path / "r")
    row = db(tmp_path / "r").execute("SELECT * FROM records WHERE review_id='r3'").fetchone()
    assert (row["status"], row["reason"], row["attempts"]) == ("quarantined", "empty_review_text", 0)
    assert out["report"]["quarantine"] == [{"review_id": "r3", "reason": "empty_review_text"}]
    pend = (tmp_path / "r" / "pending_ids.txt").read_text().split()
    assert pend == ["r1", "r2", "r4", "r5", "r6"]  # source order, quarantined excluded
    statuses = {r[0] for r in db(tmp_path / "r").execute("SELECT status FROM records")}
    assert statuses == {"pending", "quarantined"}


def test_missing_app_version_and_text_stats(tmp_path):
    out = run(FIXTURE, tmp_path / "r")
    v = out["report"]["verified_counts"]
    assert v["missing_app_version"] == 2  # r3, r4
    assert v["empty_review_text"] == 1
    assert v["distinct_nonempty_texts"] == 4  # "Great app" appears twice
    assert out["report"]["text_repeat_stats"]["rows_reusable_via_exact_text_cache"] == 1
    assert out["report"]["expectation"]["asserted"] is False
    # whitespace around text is preserved in the hash, not trimmed
    r6 = [r for r in checker.csv_rows(FIXTURE) if r["review_id"] == "r6"][0]
    assert r6["review_text"] == "  leading and trailing space  "


def test_duplicate_ids_detected(tmp_path):
    rows = [list(r.values()) for r in checker.csv_rows(FIXTURE)]
    rows.append(list(rows[0]))
    p = tmp_path / "dup.csv"
    write_csv(p, rows)
    out = run(p, tmp_path / "r")
    assert out["report"]["verified_counts"]["duplicate_review_ids"] == 1
    assert out["report"]["helper_profile"]["counts"]["duplicate_review_ids"] == 1
    assert db(tmp_path / "r").execute("SELECT COUNT(*) FROM records").fetchone()[0] == 6


def test_rerun_is_idempotent_and_keeps_completed(tmp_path):
    rd = tmp_path / "r"
    run(FIXTURE, rd)
    c = db(rd)
    c.execute("UPDATE records SET status='completed', topic='access', intent='complaint', sentiment=-0.5, severity=4, "
              "entities='[]', evidence_quote='Cannot log in', needs_review=0, label_config='x', attempts=1 WHERE review_id='r1'")
    c.commit()
    before = [tuple(r) for r in c.execute("SELECT * FROM records ORDER BY seq")]
    c.close()
    run(FIXTURE, rd)
    c = db(rd)
    after = [tuple(r) for r in c.execute("SELECT * FROM records ORDER BY seq")]
    assert before == after
    assert c.execute("SELECT status FROM records WHERE review_id='r1'").fetchone()[0] == "completed"
    assert "r1" not in (rd / "pending_ids.txt").read_text().split()


def test_changed_source_row_is_refused(tmp_path):
    rd = tmp_path / "r"
    run(FIXTURE, rd)
    rows = [list(r.values()) for r in checker.csv_rows(FIXTURE)]
    rows[1][1] = "Great app!!"  # same IDs, different text
    p = tmp_path / "changed.csv"
    write_csv(p, rows)
    with pytest.raises(PrepareError):
        run(p, rd)


def test_expect_full_fails_loudly_on_other_file(tmp_path):
    with pytest.raises(PrepareError, match="expect-full"):
        run(FIXTURE, tmp_path / "r", expect_full=True)


def test_grading_file_only_for_full_and_matches_helper(tmp_path):
    out = run(FIXTURE, tmp_path / "r", grading_dir=tmp_path / "g")
    assert out["grading_ingestion"] is None and not (tmp_path / "g").exists()
    helper_out = tmp_path / "helper.json"
    checker.write_json(helper_out, checker.profile(FIXTURE))
    assert atomic.json_text(out["report"]["helper_profile"]) == helper_out.read_text(encoding="utf-8")


def test_atomic_write_replaces_and_leaves_no_temp(tmp_path):
    p = tmp_path / "x.json"
    atomic.atomic_write_json(p, {"a": 1})
    atomic.atomic_write_json(p, {"a": 2})
    assert json.loads(p.read_text()) == {"a": 2}
    assert [f.name for f in tmp_path.iterdir()] == ["x.json"]


def test_atomic_write_failure_keeps_old_file(tmp_path, monkeypatch):
    p = tmp_path / "x.txt"
    atomic.atomic_write_text(p, "old")

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic.atomic_write_text(p, "new")
    assert p.read_text() == "old"
    assert [f.name for f in tmp_path.iterdir()] == ["x.txt"]


def test_status_check_constraint(tmp_path):
    run(FIXTURE, tmp_path / "r")
    c = db(tmp_path / "r")
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE records SET status='done' WHERE review_id='r1'")
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("UPDATE records SET status='quarantined', reason=NULL WHERE review_id='r1'")
