"""اختبارات وحدات TM355: كل خوارزمية تُختبر مقابل تعريفها أو مقابل مكتبة معروفة."""
import math
import random
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gb.tm355 import channel, errorcontrol, framecodec, huffman, infotheory, lz77, networks, securecodec  # noqa


SAMPLE = ('{"client_id":"off-1","platform":"coins","task":"round","note":"جمع العملات: جمع 6 عملات"}' * 20).encode()


# ------------------------------------------------------------ نظرية المعلومات
def test_entropy_known_values():
    assert infotheory.entropy("aaaa") == 0
    assert math.isclose(infotheory.entropy("ab"), 1.0)
    assert math.isclose(infotheory.entropy(range(256)), 8.0)
    assert math.isclose(infotheory.information(1 / 8), 3.0)


def test_shannon_capacity():
    # 1 ميجاهرتز ونسبة إشارة 30 dB (1000 مرة): C = 1e6·log2(1001) ≈ 9.97 Mbit/s
    assert math.isclose(infotheory.shannon_capacity(1e6, 30), 1e6 * math.log2(1001))


# ------------------------------------------------------------------ هوفمان
def test_huffman_round_trip_and_bounds():
    packed, code, n = huffman.encode(SAMPLE)
    assert huffman.decode(packed, code, n) == SAMPLE
    h = infotheory.entropy(SAMPLE)
    L = huffman.average_length(SAMPLE, code)
    assert h <= L < h + 1                      # نظرية شانون للترميز
    codes = list(code.values())                # ترميز بادئة: لا رمز بداية لرمز آخر
    assert not any(a != b and b.startswith(a) for a in codes for b in codes)


def test_huffman_single_symbol():
    packed, code, n = huffman.encode(b"aaaa")
    assert huffman.decode(packed, code, n) == b"aaaa"


# ------------------------------------------------------------------- LZ77
def test_lz77_round_trip_and_exploits_repeats():
    blob = lz77.encode(SAMPLE)
    assert lz77.decode(blob) == SAMPLE
    assert len(blob) < len(SAMPLE) / 5         # السجلات متكررة: LZ77 يستغل ذلك
    rnd = bytes(random.Random(1).randrange(256) for _ in range(500))
    assert lz77.decode(lz77.encode(rnd)) == rnd


def test_lz77_overlapping_copy():
    data = b"ab" * 100
    assert lz77.decode(lz77.encode(data)) == data


# --------------------------------------------------------------- الإطارات
def test_frame_delta_reconstructs_board_and_saves_bytes():
    rng = random.Random(4)
    board = ["." * 8 for _ in range(8)]
    enc, dec = framecodec.Encoder(), framecodec.Decoder()
    for _ in range(40):
        r, c = rng.randrange(8), rng.randrange(8)
        row = list(board[r]); row[c] = rng.choice("RC#.")
        board[r] = "".join(row)
        assert dec.decode(enc.encode(board)) == board
    st = enc.stats
    assert st["keyframes"] == 3 and st["sent_bytes"] < st["full_bytes"] / 2


def test_lost_frame_waits_for_next_keyframe():
    enc, dec = framecodec.Encoder(key_interval=5), framecodec.Decoder()
    frames = [enc.encode([str(i % 10) * 8]) for i in range(7)]
    assert dec.decode(frames[0]) is not None
    assert dec.decode(frames[2]) is None        # فُقد الإطار 1
    assert dec.decode(frames[3]) is None        # لا نبني على خريطة خاطئة
    assert dec.decode(frames[5]) == ["5" * 8]   # إطار مفتاحي جديد


# ------------------------------------------------------------ CRC و هامنغ
def test_crc32_matches_zlib_and_bitwise():
    for data in (b"", b"123456789", SAMPLE):
        assert errorcontrol.crc32(data) == zlib.crc32(data) == errorcontrol.crc32_bitwise(data)
    assert errorcontrol.crc32(b"123456789") == 0xCBF43926       # قيمة الفحص القياسية


def test_crc_detects_all_single_and_double_bit_errors_in_trials():
    assert errorcontrol.crc_detection_trial(SAMPLE[:300], 1, 300) == 300
    assert errorcontrol.crc_detection_trial(SAMPLE[:300], 2, 300) == 300


def test_hamming74_corrects_every_single_bit_error():
    for nibble in range(16):
        d = [(nibble >> (3 - i)) & 1 for i in range(4)]
        word = errorcontrol.hamming74_encode_nibble(d)
        for pos in range(7):
            bad = list(word); bad[pos] ^= 1
            fixed, where = errorcontrol.hamming74_decode_word(bad)
            assert fixed == d and where == pos + 1


def test_hamming_beats_uncoded_on_noisy_channel():
    r = errorcontrol.compare_over_bsc(SAMPLE, p=0.01)
    assert r["coded_bits"] == r["data_bits"] * 7 // 4
    assert r["residual_errors_coded"] < r["raw_errors"] / 3


# ---------------------------------------------------------------- القناة
def test_simulated_ber_matches_theory():
    rng = random.Random(9)
    bits = [rng.randrange(2) for _ in range(60_000)]
    for mod, ebn0 in (("BPSK", 4), ("QPSK", 4), ("16-QAM", 8)):
        sim, _ = channel.simulate_ber(mod, ebn0, bits)
        th = channel.theoretical_ber(mod, ebn0)
        assert abs(sim - th) / th < 0.25, (mod, sim, th)


def test_bpsk_reference_point_and_per():
    # BPSK عند Eb/N0 = 9.6 dB تقريباً BER = 1e-5 (قيمة معروفة في الكتب)
    assert 0.8e-5 < channel.theoretical_ber("BPSK", 9.6) < 1.2e-5
    per = channel.packet_error_rate(1e-5, 8000)
    assert math.isclose(per, 1 - (1 - 1e-5) ** 8000)
    assert math.isclose(channel.expected_transmissions(0.5), 2)


def test_networks_table():
    rows = networks.table(2300, 600)
    lte = next(r for r in rows if r["key"] == "lte")
    assert math.isclose(lte["capacity_mbps"], round(20 * math.log2(1 + 10 ** 1.5), 1))
    assert all(r["compressed_ms"] <= r["plain_ms"] for r in rows)


# ------------------------------------------------------------------- الأمن
def test_aes_gcm_and_hmac():
    key = securecodec.derive_key("pw", b"s" * 16, 1000)
    blob = securecodec.seal(key, b"s" * 16, {"x": 1})
    assert securecodec.unseal(key, blob) == {"x": 1}
    rec = {"client_id": "a", "platform": "coins", "task": "round", "played_at": "t"}
    rec["mac"] = securecodec.sign("00" * 32, rec)
    assert securecodec.verify("00" * 32, rec)
    rec["task"] = "tournament"
    assert not securecodec.verify("00" * 32, rec)
