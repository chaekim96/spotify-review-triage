"""Run one batch of at most 50 reviews through a model role, with bounded transport retries,
one retry for invalid output, and quarantine (reason + attempt count) for what still fails."""

import time
import uuid

from . import providers
from .budget import backoff_delay, estimate_tokens, usage_cost, worst_case_cost
from .labels import label_config, system_prompt, unknown_ids, user_message, validate_batch

MAX_BATCH = 50
MAX_TRANSPORT_ATTEMPTS = 4  # per request, for 429 / 5xx / timeouts / connection errors
INVALID_OUTPUT_RETRIES = 1  # the contract-style rule: retry invalid output once, then quarantine


def _request(spec, role, batch, ctx, phase, call_fn):
    """Send one request with bounded backoff. Returns (CallResult or None, list of call-log rows)."""
    version, system = system_prompt(role)
    user = user_message(batch)
    max_out = spec.max_output_tokens(len(batch))
    cfg = label_config(spec.model, spec.effort, role)
    logs = []
    for attempt in range(1, MAX_TRANSPORT_ATTEMPTS + 1):
        reserve = worst_case_cost(spec.model, estimate_tokens(system + user), max_out, ctx["rates"])
        token = ctx["ledger"].reserve(reserve, note=f"{role} {spec.name} n={len(batch)}")
        ctx["limiter"].wait()
        res = call_fn(spec, system, user, max_out)
        cost = usage_cost(spec.model, res.usage, ctx["rates"]) if res.usage else 0
        ctx["ledger"].settle(token, cost, note=res.request_id or "no-request-id")
        row = {
            "request_id": res.request_id or f"local-{uuid.uuid4()}",
            "role": role,
            "review_ids": [rid for rid, _ in batch],
            "model": spec.model,
            "phase": phase,
            "outcome": "succeeded" if res.ok else "failed",
            "label_config": cfg,
            "input_tokens": (res.usage.get("input", 0) + res.usage.get("cached_input", 0) + res.usage.get("cache_write", 0)) if res.usage else 0,
            "output_tokens": res.usage.get("output", 0) if res.usage else 0,
            # extra evidence (not in the grading schema)
            "config": spec.name, "effort": spec.effort, "prompt_version": version,
            "usage": res.usage, "cost_usd": str(cost), "reserved_usd": str(reserve),
            "latency_s": round(res.latency_s, 3), "finish": res.finish, "error": res.error,
            "transport_attempt": attempt, "max_output_tokens": max_out, "t": time.time(),
        }
        logs.append(row)
        if res.ok or not res.retryable:
            return res, logs
        time.sleep(backoff_delay(attempt))
    return None, logs


def classify_batch(spec, role, batch, ctx, phase="initial", call_fn=None):
    """Label a batch. Returns (completed, quarantined, call_logs).

    completed:   {review_id: labels}
    quarantined: {review_id: {"reason": str, "attempts": int}}
    A review is attempted at most 1 + INVALID_OUTPUT_RETRIES times for invalid output.
    """
    if not 1 <= len(batch) <= MAX_BATCH:
        raise ValueError(f"batch size {len(batch)} outside 1..{MAX_BATCH}")
    call_fn = call_fn or providers.call
    completed, quarantined, logs = {}, {}, []
    pending = list(batch)
    attempts = {rid: 0 for rid, _ in batch}
    reasons = {}
    for round_no in range(1 + INVALID_OUTPUT_RETRIES):
        if not pending:
            break
        for rid, _ in pending:
            attempts[rid] += 1
        res, rows = _request(spec, role, pending, ctx, phase, call_fn)
        logs.extend(rows)
        if res is None or not res.ok:
            err = rows[-1]["error"] if rows else "no_response"
            for rid, _ in pending:
                reasons[rid] = ["transport_failed: " + str(err)[:200]]
            if res is not None and not res.retryable:
                break  # e.g. a 400: retrying the same request will not help
            continue
        if res.finish in ("incomplete", "max_tokens"):
            rows[-1]["note"] = "output hit the token cap"
        valid, invalid = validate_batch(res.parsed, pending)
        if res.parsed is not None:
            extra = unknown_ids(res.parsed, pending)
            if extra:
                rows[-1]["unknown_ids_returned"] = extra
        completed.update(valid)
        reasons.update(invalid)
        for rid in valid:
            reasons.pop(rid, None)
        pending = [(rid, text) for rid, text in pending if rid in invalid]
    for rid, _ in batch:
        if rid not in completed:
            quarantined[rid] = {"reason": ";".join(reasons.get(rid, ["unknown"])), "attempts": attempts[rid]}
    return completed, quarantined, logs


def logged_call(spec, role, system, user, schema, name, max_out, ctx, review_ids, cfg, call_fn=None):
    """One structured call for the group or memo role, with the same budget reservation, bounded backoff
    and call logging as enrichment. Returns (parsed JSON or None, call-log rows)."""
    call_fn = call_fn or providers.call
    logs = []
    for attempt in range(1, MAX_TRANSPORT_ATTEMPTS + 1):
        reserve = worst_case_cost(spec.model, estimate_tokens(system + user), max_out, ctx["rates"])
        token = ctx["ledger"].reserve(reserve, note=f"{role} {spec.name}")
        ctx["limiter"].wait()
        res = call_fn(spec, system, user, max_out, schema, name)
        cost = usage_cost(spec.model, res.usage, ctx["rates"]) if res.usage else 0
        ctx["ledger"].settle(token, cost, note=res.request_id or "no-request-id")
        ok = res.ok and res.parsed is not None
        logs.append({
            "request_id": res.request_id or f"local-{uuid.uuid4()}", "role": role, "review_ids": list(review_ids),
            "model": spec.model, "phase": "initial", "outcome": "succeeded" if ok else "failed", "label_config": cfg,
            "input_tokens": (res.usage.get("input", 0) + res.usage.get("cached_input", 0) + res.usage.get("cache_write", 0)) if res.usage else 0,
            "output_tokens": res.usage.get("output", 0) if res.usage else 0,
            "config": spec.name, "effort": spec.effort, "usage": res.usage, "cost_usd": str(cost), "reserved_usd": str(reserve),
            "latency_s": round(res.latency_s, 3), "finish": res.finish, "error": res.error or (None if ok else "unparseable_output"),
            "transport_attempt": attempt, "max_output_tokens": max_out, "t": time.time(),
        })
        if ok:
            return res.parsed, logs
        if res.ok or not res.retryable:
            if attempt >= 2:
                break  # one retry for unparseable output, as for enrichment
            continue
        time.sleep(backoff_delay(attempt))
    return None, logs
