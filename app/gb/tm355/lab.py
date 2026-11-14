"""
«مختبر TM355»: يجمع الحسابات التي تعرضها الشاشة، على بيانات جيم بوت الحقيقية
(آخر طلب مزامنة، وإحصاءات إطارات آخر جلسة روبوت). منفصل عن الواجهة حتى يُختبر ويُستخدم في التقرير.
"""
from __future__ import annotations

import json
import random
import uuid
import zlib
from datetime import datetime, timedelta, timezone

from . import channel, errorcontrol, huffman, infotheory, lz77, networks


def sample_payload(n: int = 9, seed: int = 5) -> bytes:
    """عينة بنفس شكل طلب المزامنة الحقيقي (تُستخدم إذا لم تحدث مزامنة بعد)."""
    rng = random.Random(seed)
    notes = {"coins": "جمع العملات: جمع 6 عملات في {} خطوة", "guess": "تخمين الرقم: وجد الرقم {} في 9 محاولات"}
    t0 = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)
    recs = []
    for i in range(n):
        g = "coins" if i % 2 == 0 else "guess"
        task = "daily" if i < 2 else "round"
        rec = {"client_id": f"off-{uuid.UUID(int=rng.getrandbits(128), version=4)}", "platform": g, "task": task,
               "note": notes[g].format(rng.randrange(10, 900)),
               "played_at": (t0 + timedelta(seconds=40 * i)).isoformat()}
        rec["mac"] = f"{rng.getrandbits(256):064x}"
        recs.append(rec)
    return json.dumps({"records": recs, "sessions": [{"started_at": t0.isoformat(), "seconds": 410}]},
                      ensure_ascii=False, separators=(",", ":")).encode()


def compression(data: bytes) -> dict:
    """الإنتروبيا وثلاث طرق ضغط على نفس البايتات."""
    _, code, nbits = huffman.encode(data)
    h = infotheory.entropy(data)
    rows = {
        "original": len(data),
        "entropy_bits": round(h, 3),
        "entropy_min": round(infotheory.min_bytes(data)),
        "huffman_avg_bits": round(huffman.average_length(data, code), 3),
        "huffman_bits_only": (nbits + 7) // 8,
        "huffman": huffman.compressed_size(data),
        "lz77": len(lz77.encode(data)),
        "deflate": len(zlib.compress(data, 9)),
        "symbols": len(code),
    }
    rows["ratio_deflate"] = round(rows["original"] / rows["deflate"], 2)
    return rows


def crc_demo(data: bytes, trials: int = 200) -> dict:
    return {"crc": f"{errorcontrol.crc32(data):08x}",
            "single": errorcontrol.crc_detection_trial(data, 1, trials),
            "double": errorcontrol.crc_detection_trial(data, 2, trials),
            "burst": _burst_trial(data, trials), "trials": trials}


def _burst_trial(data: bytes, trials: int, length: int = 24) -> int:
    """أخطاء متتالية (burst) بطول 24 بت: CRC-32 يكشف كل burst طوله ≤ 32."""
    rng = random.Random(2)
    good = errorcontrol.crc32(data)
    hits = 0
    for _ in range(trials):
        start = rng.randrange(len(data) * 8 - length)
        pos = [start, start + length - 1] + [start + k for k in range(1, length - 1) if rng.random() < 0.5]
        hits += errorcontrol.crc32(errorcontrol.flip_bits(data, sorted(set(pos)))) != good
    return hits


def hamming_demo(data: bytes, p: float) -> dict:
    return errorcontrol.compare_over_bsc(data, p)


def channel_demo(mod: str, ebn0_db: float, packet_bytes: int, sim_bits: int = 24_000) -> dict:
    rng = random.Random(11)
    bits = [rng.randrange(2) for _ in range(sim_bits)]
    sim, errs = channel.simulate_ber(mod, ebn0_db, bits)
    th = channel.theoretical_ber(mod, ebn0_db)
    per = channel.packet_error_rate(th, packet_bytes * 8)
    return {"mod": mod, "ebn0_db": ebn0_db, "bits_per_symbol": channel.MODS[mod], "ber_theory": th,
            "ber_sim": sim, "sim_errors": errs, "sim_bits": len(bits), "packet_bits": packet_bytes * 8,
            "per": per, "tries": channel.expected_transmissions(per)}


def networks_demo(plain: int, packed: int) -> list[dict]:
    return networks.table(plain, packed)
