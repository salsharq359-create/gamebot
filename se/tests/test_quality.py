"""TM354: بوابة الجودة (quality gate) — تفشل إذا ساءت المقاييس أو انقطع التتبع."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from se import metrics, trace  # noqa: E402

MAX_CC = 20          # رتبة D فما فوق عند radon: «معقدة، عالية المخاطرة»


def test_no_function_above_complexity_20():
    worst = [f for f in metrics.functions(ROOT) if f["cc"] > MAX_CC]
    assert not worst, [(f["file"], f["name"], f["cc"]) for f in worst]


def test_every_requirement_is_traced_to_existing_tests():
    info = trace.check()
    assert not info["broken_refs"], info["broken_refs"]
    assert not info["untraced"], info["untraced"]
