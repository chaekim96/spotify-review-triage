"""Staged pipeline over one run folder: scope -> enrich -> verify -> group -> rank -> memo -> export.

Code owns the queue, the exact-text result cache, routing, accounting and every number.
Models only read language. All state lives in <run_dir>/state.sqlite; each batch is one transaction.
"""

import hashlib
import json
import random
import signal
import threading
import time
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from decimal import Decimal
from pathlib import Path

from . import providers, store
from .budget import BudgetExceeded, RateLimiter, SpendLedger, load_rates
from .labels import FIELDS, label_config
from .runner import MAX_BATCH, classify_batch
from .vendored import csv_rows

HARD_TEXT_CHARS = 500  # reviews at least this long are routed to the fallback model, within its cap


def text_sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_texts(csv_path, ids=None):
    out = {}
    for row in csv_rows(csv_path):
        if ids is None or row["review_id"] in ids:
            out[row["review_id"]] = row["review_text"]
    return out


def make_ctx(run_dir, budget_usd, rpm):
    """One spend ledger and one rate limiter shared by every worker. The cap covers all spend in this run folder."""
    conn = store.connect_pipeline(Path(run_dir) / "state.sqlite")
    prior = Decimal(store.get_meta(conn, "spent_usd") or "0")
    conn.close()
    ledger = SpendLedger(Decimal(str(budget_usd)), log_path=Path(run_dir) / "ledger.jsonl", spent=prior)
    return {"rates": load_rates(), "ledger": ledger, "limiter": RateLimiter(rpm)}


def save_spent(conn, ctx):
    store.set_meta(conn, "spent_usd", str(ctx["ledger"].spent))


# ---------------------------------------------------------------- scope

def set_scope(run_dir, csv_path, n=None, seed="scope-v1", include_csvs=()):
    """Declare which nonempty reviews this run classifies. n=None means every nonempty review.
    Included CSVs (dev set, golden IDs) are always in scope; the rest is a seeded hash-ordered sample."""
    conn = store.connect_pipeline(Path(run_dir) / "state.sqlite")
    rows = conn.execute("SELECT review_id FROM records WHERE status != 'quarantined' OR reason != 'empty_review_text'").fetchall()
    ids = [r[0] for r in rows]
    if n is None or n >= len(ids):
        chosen = ids
    else:
        forced = set()
        for path in include_csvs:
            forced |= {r["review_id"] for r in csv_rows(path)}
        forced &= set(ids)
        rest = sorted((i for i in ids if i not in forced), key=lambda i: hashlib.sha256(f"{seed}:{i}".encode()).hexdigest())
        chosen = sorted(forced) + rest[: max(0, n - len(forced))]
    with conn:
        conn.execute("DELETE FROM scope")
        conn.executemany("INSERT INTO scope(review_id) VALUES(?)", [(i,) for i in chosen])
        store.set_meta(conn, "scope", json.dumps({"n": len(chosen), "seed": seed, "include": [str(p) for p in include_csvs]}))
    conn.close()
    return len(chosen)


# ---------------------------------------------------------------- enrich

def _route(texts_by_rep, fallback_quota):
    """Deterministic routing: the longest reviews (>= HARD_TEXT_CHARS) go to the fallback model, up to its quota."""
    hard = sorted((rid for rid, t in texts_by_rep.items() if len(t) >= HARD_TEXT_CHARS), key=lambda r: -len(texts_by_rep[r]))
    return set(hard[:fallback_quota])


def _write_batch(conn, done, quar, logs, spec_cfg, calls_path, sha_of):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with conn:
        for rid, lab in done.items():
            conn.execute(
                "UPDATE records SET status='completed', reason=NULL, topic=?, intent=?, sentiment=?, severity=?, entities=?, "
                "evidence_quote=?, needs_review=?, label_config=?, cache_source_id=NULL, attempts=attempts+1, updated_at=? "
                "WHERE review_id=? AND status='pending'",
                (lab["topic"], lab["intent"], lab["sentiment"], lab["severity"], json.dumps(lab["entities"], ensure_ascii=False),
                 lab["evidence_quote"], int(lab["needs_review"]), spec_cfg, now, rid))
            # exact-text cache: every other pending in-scope review with the identical text reuses this result
            conn.execute(
                "UPDATE records SET status='completed', reason=NULL, topic=?, intent=?, sentiment=?, severity=?, entities=?, "
                "evidence_quote=?, needs_review=?, label_config=?, cache_source_id=?, updated_at=? "
                "WHERE text_sha256=? AND status='pending' AND review_id IN (SELECT review_id FROM scope)",
                (lab["topic"], lab["intent"], lab["sentiment"], lab["severity"], json.dumps(lab["entities"], ensure_ascii=False),
                 lab["evidence_quote"], int(lab["needs_review"]), spec_cfg, rid, now, sha_of[rid]))
        for rid, q in quar.items():
            conn.execute("UPDATE records SET status='quarantined', reason=?, attempts=attempts+?, updated_at=? WHERE review_id=? AND status='pending'",
                         (q["reason"], q["attempts"], now, rid))
        for row in logs:
            conn.execute("INSERT OR REPLACE INTO calls(request_id, role, phase, outcome, row) VALUES(?,?,?,?,?)",
                         (row["request_id"], row["role"], row["phase"], row["outcome"], json.dumps(row, ensure_ascii=False)))
    with open(calls_path, "a", encoding="utf-8") as f:
        for row in logs:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _alias_from_cache(conn, cache_db, cfg_by_rid, sha_of):
    """Warm-run result cache: reuse a completed original from another run folder with identical text and label_config."""
    if not cache_db:
        return 0
    src = store.connect(cache_db)
    hits = 0
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with conn:
        for rid, cfg in cfg_by_rid.items():
            row = src.execute(
                "SELECT review_id, topic, intent, sentiment, severity, entities, evidence_quote, needs_review FROM records "
                "WHERE text_sha256=? AND label_config=? AND status='completed' AND cache_source_id IS NULL LIMIT 1",
                (sha_of[rid], cfg)).fetchone()
            if row:
                conn.execute(
                    "UPDATE records SET status='completed', topic=?, intent=?, sentiment=?, severity=?, entities=?, evidence_quote=?, "
                    "needs_review=?, label_config=?, cache_source_id=?, updated_at=? WHERE review_id=? AND status='pending'",
                    (*row[1:], cfg, row[0], now, rid))
                hits += 1
    src.close()
    return hits


def enrich(run_dir, texts, primary, fallback=None, ctx=None, phase=None, workers=1, batch_size=MAX_BATCH,
           fallback_fraction=0.02, stop_after_batches=None, cache_db=None, log=print):
    """Classify every pending in-scope review. Returns a summary dict. Safe to interrupt and rerun."""
    run_dir = Path(run_dir)
    conn = store.connect_pipeline(run_dir / "state.sqlite")
    calls_path = run_dir / "calls.jsonl"
    if phase is None:
        phase = "resume" if conn.execute("SELECT 1 FROM calls WHERE role='enrich' LIMIT 1").fetchone() else "initial"
    primary_cfg = label_config(primary.model, primary.effort)
    fallback_cfg = label_config(fallback.model, fallback.effort) if fallback else None
    sha_of = dict(conn.execute("SELECT r.review_id, r.text_sha256 FROM records r JOIN scope s USING(review_id)"))
    n_scope_distinct = len(set(sha_of.values()))
    fallback_quota = int(fallback_fraction * n_scope_distinct) if fallback else 0
    fallback_used = conn.execute("SELECT COUNT(*) FROM records r JOIN scope s USING(review_id) WHERE label_config=? AND cache_source_id IS NULL",
                                 (fallback_cfg,)).fetchone()[0] if fallback else 0
    t0 = time.perf_counter()
    stats = defaultdict(int)
    submitted = 0
    stop = threading.Event()
    prev_handler = signal.getsignal(signal.SIGINT)

    def on_sigint(sig, frame):
        log("interrupt received: finishing in-flight batches, then saving and stopping")
        stop.set()
    signal.signal(signal.SIGINT, on_sigint)
    try:
        for pass_no in (1, 2):  # pass 2 retries texts whose first representative was quarantined, with a new representative
            pending = [r for (r,) in conn.execute(
                "SELECT r.review_id FROM records r JOIN scope s USING(review_id) WHERE r.status='pending' ORDER BY r.seq")]
            if not pending or stop.is_set():
                break
            reps = {}
            for rid in pending:
                reps.setdefault(sha_of[rid], rid)
            rep_texts = {rid: texts[rid] for rid in reps.values()}
            hard = _route(rep_texts, max(0, fallback_quota - fallback_used))
            cfg_by_rid = {rid: (fallback_cfg if rid in hard else primary_cfg) for rid in rep_texts}
            hits = _alias_from_cache(conn, cache_db, cfg_by_rid, sha_of)
            stats["result_cache_hits_from_cache_db"] += hits
            if hits:
                pending = [r for (r,) in conn.execute(
                    "SELECT r.review_id FROM records r JOIN scope s USING(review_id) WHERE r.status='pending' ORDER BY r.seq")]
                reps = {}
                for rid in pending:
                    reps.setdefault(sha_of[rid], rid)
                rep_texts = {rid: texts[rid] for rid in reps.values()}
                hard &= set(rep_texts)
            queue = []
            for spec, ids in ((primary, [r for r in rep_texts if r not in hard]), (fallback, [r for r in rep_texts if r in hard])):
                for i in range(0, len(ids), batch_size):
                    queue.append((spec, [(rid, rep_texts[rid]) for rid in ids[i:i + batch_size]]))
            log(f"pass {pass_no}: {len(pending)} pending in scope, {len(rep_texts)} distinct texts to send, "
                f"{len(hard)} routed to fallback, {len(queue)} requests, phase={phase}, workers={workers}")
            for spec in {s.provider: s for s, _ in queue}.values():
                providers._client(spec.provider)  # create clients before threads start
            with ThreadPoolExecutor(max_workers=workers) as pool:
                inflight = {}
                qi = 0
                while qi < len(queue) or inflight:
                    while (qi < len(queue) and len(inflight) < workers and not stop.is_set()
                           and (stop_after_batches is None or submitted < stop_after_batches)):
                        spec, batch = queue[qi]
                        qi += 1
                        submitted += 1
                        inflight[pool.submit(classify_batch, spec, "enrich", batch, ctx, phase)] = (spec, batch)
                    if not inflight:
                        break
                    finished, _ = wait(inflight, return_when=FIRST_COMPLETED)
                    for fut in finished:
                        spec, batch = inflight.pop(fut)
                        try:
                            done, quar, logs = fut.result()
                        except BudgetExceeded as e:
                            log(f"budget stop: {e}")
                            stop.set()
                            continue
                        cfg = label_config(spec.model, spec.effort)
                        _write_batch(conn, done, quar, logs, cfg, calls_path, sha_of)
                        with conn:
                            save_spent(conn, ctx)
                        stats["completed_by_model"] += len(done)
                        stats["quarantined"] += len(quar)
                        stats["requests"] += len(logs)
                        stats["batches"] += 1
                        if stats["batches"] % 20 == 0:
                            log(f"  {stats['batches']} batches, spent ${ctx['ledger'].spent:.4f}, {time.perf_counter() - t0:.0f}s")
                    if stop_after_batches is not None and submitted >= stop_after_batches and not inflight:
                        stop.set()
            if stop.is_set():
                break
        # texts whose representatives failed twice: the remaining copies are quarantined with a reason
        if not stop.is_set():
            with conn:
                conn.execute(
                    "UPDATE records SET status='quarantined', reason='same_text_as_quarantined_review', updated_at=? "
                    "WHERE status='pending' AND review_id IN (SELECT review_id FROM scope)",
                    (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),))
    finally:
        signal.signal(signal.SIGINT, prev_handler)
    counts = store.status_counts(conn)
    aliases = conn.execute("SELECT COUNT(*) FROM records WHERE cache_source_id IS NOT NULL").fetchone()[0]
    conn.close()
    out = {"phase": phase, "interrupted": stop.is_set(), "wall_seconds": round(time.perf_counter() - t0, 2),
           "spent_usd_total": str(ctx["ledger"].spent), "statuses": counts, "cache_aliases": aliases, **stats}
    log(json.dumps(out))
    return out


def checkpoint(run_dir, path):
    conn = store.connect_pipeline(Path(run_dir) / "state.sqlite")
    ids = [r for (r,) in conn.execute("SELECT review_id FROM records WHERE status='completed' ORDER BY review_id")]
    conn.close()
    from .atomic import atomic_write_json
    atomic_write_json(path, {"completed_ids": ids})
    return len(ids)


# ---------------------------------------------------------------- verify

def verify(run_dir, texts, spec, ctx, fraction, seed="verify-v1", workers=1, batch_size=MAX_BATCH, cache_db=None, log=print):
    """Independent verifier: re-labels a declared random sample of model-labeled originals without seeing the
    first labels. Code compares afterwards (see verify_report)."""
    run_dir = Path(run_dir)
    conn = store.connect_pipeline(run_dir / "state.sqlite")
    originals = [r for (r,) in conn.execute(
        "SELECT review_id FROM records WHERE status='completed' AND cache_source_id IS NULL ORDER BY review_id")]
    k = max(1, round(fraction * len(originals)))
    sample = sorted(random.Random(seed).sample(originals, min(k, len(originals))))
    todo = [r for r in sample if not conn.execute("SELECT 1 FROM verify WHERE review_id=?", (r,)).fetchone()]
    cfg = label_config(spec.model, spec.effort, role="verify")
    if cache_db:  # warm run: reuse verifier results for identical text under the identical verifier config
        src = store.connect(cache_db)
        reused = 0
        with conn:
            for rid in list(todo):
                sha = conn.execute("SELECT text_sha256 FROM records WHERE review_id=?", (rid,)).fetchone()[0]
                hit = src.execute("SELECT v.labels FROM verify v JOIN records r USING(review_id) WHERE r.text_sha256=? AND v.label_config=?",
                                  (sha, cfg)).fetchone()
                if hit:
                    conn.execute("INSERT OR REPLACE INTO verify(review_id, labels, label_config) VALUES(?,?,?)", (rid, hit[0], cfg))
                    todo.remove(rid)
                    reused += 1
        src.close()
        log(f"verify: {reused} results reused from the saved cache")
    batches = [[(r, texts[r]) for r in todo[i:i + batch_size]] for i in range(0, len(todo), batch_size)]
    providers._client(spec.provider)
    log(f"verify: {len(originals)} originals, declared sample {len(sample)} ({fraction:.0%}), {len(batches)} requests")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for done, quar, logs in pool.map(lambda b: classify_batch(spec, "verify", b, ctx, "initial"), batches):
            with conn:
                for rid, lab in done.items():
                    conn.execute("INSERT OR REPLACE INTO verify(review_id, labels, label_config) VALUES(?,?,?)",
                                 (rid, json.dumps(lab, ensure_ascii=False), cfg))
                for row in logs:
                    conn.execute("INSERT OR REPLACE INTO calls(request_id, role, phase, outcome, row) VALUES(?,?,?,?,?)",
                                 (row["request_id"], row["role"], row["phase"], row["outcome"], json.dumps(row, ensure_ascii=False)))
                save_spent(conn, ctx)
            with open(run_dir / "calls.jsonl", "a", encoding="utf-8") as f:
                for row in logs:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
    store.set_meta(conn, "verify_sample", json.dumps({"fraction": fraction, "seed": seed, "n": len(sample)}))
    conn.commit()
    conn.close()
    return sample


def load_records(conn, completed_only=True):
    q = ("SELECT review_id, source_sha256, status, reason, topic, intent, sentiment, severity, entities, evidence_quote, "
         "needs_review, label_config, cache_source_id, attempts FROM records")
    if completed_only:
        q += " WHERE status='completed'"
    out = {}
    for row in conn.execute(q + " ORDER BY seq"):
        rid = row[0]
        out[rid] = {"review_id": rid, "source_sha256": row[1], "status": row[2], "reason": row[3], "attempts": row[13]}
        if row[2] == "completed":
            out[rid].update(topic=row[4], intent=row[5], sentiment=row[6], severity=row[7], entities=json.loads(row[8]),
                            evidence_quote=row[9], needs_review=bool(row[10]), label_config=row[11])
            if row[12]:
                out[rid]["cache_source_id"] = row[12]
    return out


def verify_report(run_dir):
    """Code compares verifier labels with the first labels on the declared sample."""
    from .evaluate import score
    conn = store.connect_pipeline(Path(run_dir) / "state.sqlite")
    ver = {rid: json.loads(lab) for rid, lab in conn.execute("SELECT review_id, labels FROM verify")}
    recs = load_records(conn)
    meta = json.loads(store.get_meta(conn, "verify_sample") or "{}")
    conn.close()
    first = {rid: {k: recs[rid][k] for k in FIELDS} for rid in ver if rid in recs}
    m = score(first, ver)  # verifier labels as the reference, first labels as predictions
    return {"declared_sample": meta, "n_verified": len(ver), **{k: v for k, v in m.items() if k != "disagreements"},
            "disagreements": m["disagreements"]}
