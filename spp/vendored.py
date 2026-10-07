"""Load the vendored course checker so hashing and profiling cannot drift from the contract."""

import hashlib
import importlib.util
from pathlib import Path

VENDOR_PATH = Path(__file__).resolve().parents[1] / "vendor" / "check_submission.py"
# sha256 of the instructor-provided check_submission.py (a5-audit-v1). Verified at import.
VENDOR_SHA256 = "d60bd66d84922d934c65b3d42b2c7d36cc738e8c75e2d6f2b2f58bca3141c26d"


def _load():
    actual = hashlib.sha256(VENDOR_PATH.read_bytes()).hexdigest()
    if actual != VENDOR_SHA256:
        raise RuntimeError(
            f"vendor/check_submission.py was modified (sha256 {actual}, expected {VENDOR_SHA256}). "
            "Restore the verbatim copy from the course files."
        )
    spec = importlib.util.spec_from_file_location("check_submission", VENDOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load()
row_sha = checker.row_sha
profile = checker.profile
csv_rows = checker.csv_rows
FIELDS = checker.FIELDS
