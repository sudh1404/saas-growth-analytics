"""The synthetic data generator must be reproducible: same seed -> byte-identical files."""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(out: Path):
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_data.py"), "--small", "--out", str(out)],
                   check=True, capture_output=True)
    return {f.name: hashlib.md5(f.read_bytes()).hexdigest() for f in sorted(out.glob("*.csv"))}


def test_generator_is_deterministic(tmp_path):
    a, b = _run(tmp_path / "a"), _run(tmp_path / "b")
    assert len(a) == 9
    assert a == b
