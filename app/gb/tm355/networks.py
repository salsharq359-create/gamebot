"""
مقارنة الشبكات بسعة شانون (TM355 — الاتصالات المتنقلة والثابتة).

القيم أدناه **افتراضات تعليمية** لظروف نموذجية (عرض القناة ونسبة الإشارة إلى الضوضاء)،
وليست قياسات. الهدف مقارنة الحد الأعلى النظري، ثم حساب زمن إرسال طلب مزامنة جيم بوت.
زمن الإرسال = زمن الذهاب والإياب (RTT) + الحجم ÷ المعدل الفعلي.
والمعدل الفعلي أقل كثيراً من سعة شانون (الترويسات، والمشاركة مع مستخدمين آخرين، وغيرها)،
لذلك نفترض أن المستخدم يحصل على نسبة efficiency من السعة.
"""
from __future__ import annotations

from dataclasses import dataclass

from .infotheory import shannon_capacity


@dataclass(frozen=True)
class Profile:
    key: str
    name: str
    bandwidth_mhz: float
    snr_db: float
    rtt_ms: float
    efficiency: float          # نسبة السعة التي يحصل عليها المستخدم فعلياً


PROFILES = [
    Profile("edge", "2G EDGE", 0.2, 10, 300, 0.25),
    Profile("3g", "3G HSPA", 5, 8, 120, 0.25),
    Profile("lte", "4G LTE", 20, 15, 50, 0.25),
    Profile("nr", "5G NR (3.5 GHz)", 100, 20, 20, 0.25),
    Profile("wifi6", "Wi-Fi 6 (80 MHz)", 80, 25, 8, 0.4),
    Profile("vdsl", "VDSL2 (17a)", 17.664, 30, 15, 0.35),
]


def capacity_mbps(p: Profile) -> float:
    return shannon_capacity(p.bandwidth_mhz * 1e6, p.snr_db) / 1e6


def transfer_ms(p: Profile, nbytes: int) -> float:
    rate_bps = capacity_mbps(p) * 1e6 * p.efficiency
    return p.rtt_ms + nbytes * 8 / rate_bps * 1000


def table(nbytes_plain: int, nbytes_compressed: int) -> list[dict]:
    rows = []
    for p in PROFILES:
        rows.append({"key": p.key, "name": p.name, "bandwidth_mhz": p.bandwidth_mhz, "snr_db": p.snr_db,
                     "capacity_mbps": round(capacity_mbps(p), 1), "rtt_ms": p.rtt_ms,
                     "plain_ms": round(transfer_ms(p, nbytes_plain), 2),
                     "compressed_ms": round(transfer_ms(p, nbytes_compressed), 2)})
    return rows
