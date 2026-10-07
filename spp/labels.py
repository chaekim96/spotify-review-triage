"""Shared label vocabulary, the model output schema, prompt assembly and output validation.

Code owns validation: every returned item is checked against the IDs that were sent, the
contract's enums and ranges, and an exact-substring test for the evidence quote.
"""

import hashlib
import json
import math
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

TOPICS = ("access", "usability", "playback", "downloads", "catalog", "billing", "support", "other")
INTENTS = ("cancellation", "complaint", "request", "praise", "unclear")  # precedence order
SEVERITIES = (1, 2, 3, 4, 5)

SCHEMA_VERSION = "schema-v1"
LABELS_VERSION = "labels-v1"
FIELDS = ("topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review")

# JSON schema sent to providers for structured output. Range checks (sentiment, severity) are
# enforced in validate_item because not every provider accepts numeric constraints.
ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "review_id": {"type": "string"},
        "topic": {"type": "string", "enum": list(TOPICS)},
        "intent": {"type": "string", "enum": list(INTENTS)},
        "sentiment": {"type": "number"},
        "severity": {"type": "integer", "enum": list(SEVERITIES)},
        "entities": {"type": "array", "items": {"type": "string"}},
        "evidence_quote": {"type": "string"},
        "needs_review": {"type": "boolean"},
    },
    "required": ["review_id", *FIELDS],
    "additionalProperties": False,
}
BATCH_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": ITEM_SCHEMA}},
    "required": ["items"],
    "additionalProperties": False,
}

ROLE_PROMPTS = {"enrich": "enrich-v1", "verify": "verify-v1"}


def _read(name):
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def load_examples(name="examples_v1.jsonl"):
    return [json.loads(line) for line in _read(name).splitlines() if line.strip()]


def _render_examples(examples):
    blocks = []
    for ex in examples:
        out = {k: ex[k] for k in FIELDS}
        blocks.append(
            f"Review: {json.dumps(ex['review_text'], ensure_ascii=False)}\n"
            f"Labels: {json.dumps(out, ensure_ascii=False)}\n"
            f"Why: {ex['why']}"
        )
    return "\n\n".join(blocks)


def system_prompt(role):
    """Assemble the versioned system prompt for a role ('enrich' or 'verify')."""
    version = ROLE_PROMPTS[role]
    template = _read(f"{role}_v1.md")
    labels = _read("labels_v1.md").strip()
    text = template.replace("{labels}", labels)
    if "{examples}" in text:
        text = text.replace("{examples}", _render_examples(load_examples()))
    return version, text


def prompt_sha256(role):
    return hashlib.sha256(system_prompt(role)[1].encode("utf-8")).hexdigest()


def user_message(batch):
    """batch: list of (review_id, review_text). Reviews are passed as data, never as instructions."""
    payload = [{"review_id": rid, "review_text": text} for rid, text in batch]
    return "<reviews>\n" + json.dumps(payload, ensure_ascii=False, indent=0) + "\n</reviews>"


def label_config(model, effort, role="enrich"):
    """The contract's model+prompt+schema-version string. One per (model, effort, prompt, schema)."""
    return f"{model}+{effort}+{ROLE_PROMPTS[role]}+{LABELS_VERSION}+{SCHEMA_VERSION}"


def validate_item(item, text):
    """Return a list of problems with one returned item (empty list = valid)."""
    problems = []
    if not isinstance(item, dict):
        return ["item_not_object"]
    extra = set(item) - {"review_id", *FIELDS}
    if extra:
        problems.append("extra_fields:" + ",".join(sorted(extra)))
    missing = [f for f in FIELDS if f not in item]
    if missing:
        problems.append("missing_fields:" + ",".join(missing))
        return problems
    if item["topic"] not in TOPICS:
        problems.append("bad_topic")
    if item["intent"] not in INTENTS:
        problems.append("bad_intent")
    sev = item["severity"]
    if type(sev) is not int or sev not in SEVERITIES:  # bool is excluded on purpose
        problems.append("bad_severity")
    s = item["sentiment"]
    if type(s) not in (int, float) or not math.isfinite(s) or not -1 <= s <= 1:
        problems.append("bad_sentiment")
    ents = item["entities"]
    if not isinstance(ents, list) or not all(isinstance(e, str) and e.strip() for e in ents):
        problems.append("bad_entities")
    q = item["evidence_quote"]
    if not isinstance(q, str) or not q:
        problems.append("empty_quote")
    elif q not in text:
        problems.append("quote_not_substring")
    if type(item["needs_review"]) is not bool:
        problems.append("bad_needs_review")
    return problems


def validate_batch(parsed, batch):
    """Check a parsed provider response against the batch that was sent.

    Returns (valid, invalid): valid maps review_id -> cleaned labels; invalid maps review_id -> reasons.
    A bad item never discards its valid siblings.
    """
    texts = dict(batch)
    valid, invalid = {}, {}
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return {}, {rid: ["unparseable_response"] for rid in texts}
    seen = {}
    for item in items:
        rid = item.get("review_id") if isinstance(item, dict) else None
        if rid not in texts:
            continue  # unknown or hallucinated ID: ignored, the sent ID stays missing below
        seen.setdefault(rid, []).append(item)
    for rid, text in texts.items():
        got = seen.get(rid, [])
        if not got:
            invalid[rid] = ["missing_id"]
        elif len(got) > 1:
            invalid[rid] = ["duplicate_id"]
        else:
            problems = validate_item(got[0], text)
            if problems:
                invalid[rid] = problems
            else:
                valid[rid] = {k: got[0][k] for k in FIELDS}
    return valid, invalid


def unknown_ids(parsed, batch):
    """IDs the model returned that were never sent (logged as evidence of a bad response)."""
    sent = {rid for rid, _ in batch}
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        return []
    return sorted({str(i.get("review_id")) for i in items if isinstance(i, dict) and i.get("review_id") not in sent})
