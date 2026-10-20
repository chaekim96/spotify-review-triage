"""Local hand-labeling helper for the golden 50. No model call, no network beyond localhost.

    uv run python tools/label_golden.py            # then open http://localhost:8765

Shows one review at a time; you choose every label yourself. Each "Save" rewrites
data_raw/golden_50_to_label.csv atomically (same columns, same row order, review columns untouched).
"""

import csv
import io
import json
import os
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = Path(os.environ.get("GOLDEN_CSV", ROOT / "data_raw" / "golden_50_to_label.csv"))
PAGE = Path(__file__).with_name("label_golden.html")
LABELS = ["topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review"]
TOPICS = {"access", "usability", "playback", "downloads", "catalog", "billing", "support", "other"}
INTENTS = {"cancellation", "complaint", "request", "praise", "unclear"}


def read_rows():
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def write_rows(fields, rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    fd, tmp = tempfile.mkstemp(dir=CSV_PATH.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(buf.getvalue())
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CSV_PATH)


def validate(row, labels):
    errs = []
    if labels.get("topic") not in TOPICS:
        errs.append("choose a topic")
    if labels.get("intent") not in INTENTS:
        errs.append("choose an intent")
    try:
        s = float(labels.get("sentiment"))
        if not -1 <= s <= 1:
            errs.append("sentiment must be between -1 and 1")
    except (TypeError, ValueError):
        errs.append("sentiment must be a number")
    if str(labels.get("severity")) not in {"1", "2", "3", "4", "5"}:
        errs.append("choose a severity 1-5")
    ents = labels.get("entities")
    if not isinstance(ents, list) or not all(isinstance(e, str) and e.strip() for e in ents):
        errs.append("entities must be a list of non-empty strings")
    q = labels.get("evidence_quote") or ""
    if not q:
        errs.append("evidence quote is required")
    elif q not in row["review_text"]:
        errs.append("evidence quote must be copied exactly from the review")
    if labels.get("needs_review") not in (True, False):
        errs.append("needs_review must be true or false")
    return errs


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, PAGE.read_bytes(), "text/html")
        if self.path == "/api/rows":
            _, rows = read_rows()
            out = []
            for r in rows:
                ents = r.get("entities") or ""
                try:
                    ents = json.loads(ents) if ents.strip() else None
                except ValueError:
                    ents = None
                out.append({"review_id": r["review_id"], "review_text": r["review_text"], "topic": r["topic"], "intent": r["intent"],
                            "sentiment": r["sentiment"], "severity": r["severity"], "entities": ents,
                            "evidence_quote": r["evidence_quote"], "needs_review": r["needs_review"]})
            return self._send(200, out)
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/save":
            return self._send(404, {"error": "not found"})
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        fields, rows = read_rows()
        idx = next((i for i, r in enumerate(rows) if r["review_id"] == body.get("review_id")), None)
        if idx is None:
            return self._send(400, {"errors": ["unknown review_id"]})
        labels = body.get("labels", {})
        errs = validate(rows[idx], labels)
        if errs:
            return self._send(400, {"errors": errs})
        rows[idx].update({
            "topic": labels["topic"], "intent": labels["intent"], "sentiment": str(round(float(labels["sentiment"]), 2)),
            "severity": str(int(labels["severity"])), "entities": json.dumps(labels["entities"], ensure_ascii=False),
            "evidence_quote": labels["evidence_quote"], "needs_review": "true" if labels["needs_review"] else "false",
        })
        write_rows(fields, rows)
        done = sum(1 for r in rows if r["topic"].strip())
        self._send(200, {"ok": True, "labeled": done, "total": len(rows)})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"Golden-50 labeling helper: http://localhost:{port}  (Ctrl+C to stop). Saving to {CSV_PATH}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
