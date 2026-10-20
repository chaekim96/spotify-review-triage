"""End-to-end offline test: prepare -> scope -> enrich (interrupt + resume, exact-text cache, 2 workers) ->
verify -> group -> rank -> memo -> export, then the course checker. Providers are fakes; no network."""

import csv
import json
import re

import pytest

from spp import analysis, pipeline, providers, runner
from spp.prepare import prepare
from spp.providers import CallResult, get_spec
from spp.vendored import checker

TEXTS = [
    "Cannot log in after the update",
    "Songs keep stopping in the middle, playback is broken",
    "Too many ads between every song",
    "Great app",
    "Great app",                                   # exact duplicate -> cache alias
    "Downloads disappear when offline",
    "Songs keep stopping in the middle, playback is broken",
    "Love the recommendations",
    "Charged twice for premium and no refund",
    "App crashes on start, playback impossible",
] * 3


def _make_csv(path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "review_text", "review_rating", "review_likes", "app_version", "review_timestamp"])
        for i, t in enumerate(TEXTS):
            w.writerow([f"id{i:03d}", t, "1", "0", "8.8.1", f"2023-0{1 + i % 9}-01 10:00:00"])
        w.writerow(["empty1", "", "3", "0", "", "2023-02-02 10:00:00"])


def _labels_for(text):
    low = text.lower()
    if "log in" in low:
        return "access", "complaint", 4
    if "playback" in low or "crash" in low:
        return "playback", "complaint", 4
    if "ads" in low:
        return "usability", "complaint", 2
    if "download" in low:
        return "downloads", "complaint", 3
    if "charged" in low:
        return "billing", "cancellation", 5
    return "other", "praise", 1


def fake_call(spec, system, user, max_out, schema=None, name=None):
    usage = {"input": 500, "cached_input": 0, "cache_write": 0, "output": 100, "reasoning": 0}
    if name == "issue_groups":
        topic = json.loads(user)["topic"]
        kw = {"playback": ["stopping", "crash"], "access": ["log in"], "usability": ["ads"]}.get(topic, ["zzz"])
        parsed = {"issues": [{"name": f"{topic} issue", "description": "d", "keywords": kw}]}
    elif name == "memo":
        payload = json.loads(user.split("\n\nYour previous")[0])
        top = payload["top_issues"][0]
        parsed = {"memo_markdown": f"# Recommendation\nFix {top['issue_id']} first: severity sum {top['severity_sum']['value']} "
                                   f"[{top['severity_sum']['claim_id']}].", "recommended_area": top["area"], "cited_claim_ids": []}
    else:
        items = json.loads(user.split("<reviews>\n")[1].rsplit("\n</reviews>")[0])
        out = []
        for it in items:
            topic, intent, sev = _labels_for(it["review_text"])
            out.append({"review_id": it["review_id"], "topic": topic, "intent": intent, "sentiment": -0.5 if sev > 1 else 0.8,
                        "severity": sev, "entities": [], "evidence_quote": it["review_text"][:20], "needs_review": False})
        parsed = {"items": out}
    fake_call.n += 1
    return CallResult(True, False, parsed, usage, f"req-{spec.name}-{fake_call.n}", 0.01, "completed")


fake_call.n = 0


@pytest.fixture(autouse=True)
def patched(monkeypatch):
    monkeypatch.setattr(providers, "call", fake_call)
    monkeypatch.setattr(providers, "_client", lambda p: None)
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)


def test_full_pipeline_with_interrupt_resume_and_checker(tmp_path):
    csv_path = tmp_path / "in.csv"
    _make_csv(csv_path)
    run = tmp_path / "run"
    prepare(csv_path, run)
    assert pipeline.set_scope(run, csv_path) == len(TEXTS)
    texts = pipeline.load_texts(csv_path)
    ctx = pipeline.make_ctx(run, 1.0, rpm=100_000)
    primary, fallback = get_spec("luna-none"), get_spec("sonnet-low")

    # interrupt after one batch of 4 distinct texts, snapshot, then resume
    first = pipeline.enrich(run, texts, primary, fallback, ctx, phase="initial", workers=1, batch_size=4, stop_after_batches=1, log=lambda *a: None)
    assert first["interrupted"]
    (run / "checkpoints").mkdir()
    n_before = pipeline.checkpoint(run, run / "checkpoints" / "checkpoint_before.json")
    assert n_before > 4                              # 4 originals + their exact-text aliases
    second = pipeline.enrich(run, texts, primary, fallback, ctx, phase="resume", workers=2, batch_size=4, log=lambda *a: None)
    assert not second["interrupted"] and second["statuses"]["pending"] == 0
    pipeline.checkpoint(run, run / "checkpoints" / "checkpoint_after.json")

    pipeline.verify(run, texts, get_spec("haiku"), ctx, fraction=0.5, log=lambda *a: None)
    rep = pipeline.verify_report(run)
    assert rep["topic_agreement"] == 1.0

    analysis.group(run, texts, get_spec("luna-low"), ctx, cache_dir=tmp_path / "cache", log=lambda *a: None)
    rows, claims, aggregates, issues = analysis.rank(run)
    ranking_bytes = (run / "outputs" / "ranking.csv").read_bytes()
    analysis.rank(run)                                # rerank from saved files only: identical bytes
    assert (run / "outputs" / "ranking.csv").read_bytes() == ranking_bytes
    analysis.memo(run, texts, get_spec("sonnet-low"), ctx, cache_dir=tmp_path / "cache", log=lambda *a: None)
    assert re.search(r"\[C\d{4}\]", (run / "outputs" / "memo.md").read_text())

    g = tmp_path / "grading"
    checker.write_json(g / "ingestion.json", checker.profile(csv_path))
    analysis.export(run, g, g / "ingestion.json")
    ref = checker.reference(csv_path, csv_path)
    result = checker.audit(g, ref)
    issues_found = set(result["issue_counts"]) - {"run_manifest_mismatch"}  # run.json names the real 660,622-row file
    assert issues_found == set(), result["examples"]
    assert result["coverage"]["valid_cache_reuses"] > 0
    assert result["working_coverage_point_candidate"] == 1.0


def test_memo_checker_rejects_invented_numbers_and_ids():
    claims = [{"claim_id": "C0001", "issue_id": "PLAYBACK-01", "metric": "severity_sum", "value": "40"}]
    issues = {"PLAYBACK-01": {}}
    ok = analysis.check_memo("Fix PLAYBACK-01: severity sum 40 [C0001].", claims, issues, set(), {"40"})
    assert ok == []
    bad = analysis.check_memo("Fix PLAYBACK-02: 4,000 users churned [C0009].", claims, issues, set(), {"40"})
    assert any("C0009" in p for p in bad) and any("PLAYBACK-02" in p for p in bad) and any("4,000" in p for p in bad)


def test_rerank_from_grading_matches_export(tmp_path):
    test_full_pipeline_with_interrupt_resume_and_checker(tmp_path)
    g = tmp_path / "grading"
    rank_txt, claims_txt = analysis.rerank_from_grading(g)
    assert rank_txt == (g / "ranking.csv").read_text()
    assert claims_txt == (g / "claims.csv").read_text()
