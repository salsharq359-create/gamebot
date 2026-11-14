"""
TM354 (الوحدة 7): التصميم بالعقود (Design by Contract).

كل عملية لها:
  * شرط مسبق (precondition): ما يجب أن يضمنه المستدعي قبل الاستدعاء
  * شرط لاحق (postcondition): ما تضمنه العملية عند انتهائها
  * ثابت (invariant): ما يبقى صحيحاً دائماً للكائن أو للنظام

المزخرفات هنا تفحص العقد وقت التشغيل وترفع ContractError عند الخرق، فيظهر الخطأ في مكانه
بدل أن ينتشر بيانات خاطئة. يمكن إيقاف الفحص في الإنتاج بمتغير البيئة GAMEBOT_CONTRACTS=0.
"""
from __future__ import annotations

import functools
import inspect
import os
from typing import Callable

ENABLED = os.environ.get("GAMEBOT_CONTRACTS", "1") != "0"


class ContractError(AssertionError):
    """خرق عقد: خطأ برمجي (وليس خطأ مستخدم)، لذلك يرث من AssertionError."""


def requires(check: Callable[..., bool], message: str):
    """شرط مسبق: check يأخذ نفس وسائط الدالة."""
    def deco(fn):
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if ENABLED:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                if not check(**bound.arguments):
                    raise ContractError(f"شرط مسبق مخروق في {fn.__name__}: {message}")
            return fn(*args, **kwargs)
        wrapper.__contracts__ = getattr(fn, "__contracts__", []) + [("pre", message)]
        return wrapper
    return deco


def ensures(check: Callable[..., bool], message: str):
    """شرط لاحق: check يأخذ result ثم نفس وسائط الدالة."""
    def deco(fn):
        sig = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            if ENABLED:
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                if not check(result, **bound.arguments):
                    raise ContractError(f"شرط لاحق مخروق في {fn.__name__}: {message}")
            return result
        wrapper.__contracts__ = getattr(fn, "__contracts__", []) + [("post", message)]
        return wrapper
    return deco


def check_invariant(condition: bool, message: str) -> None:
    """ثابت النظام: يُستدعى بعد أي عملية تغيّر الحالة."""
    if ENABLED and not condition:
        raise ContractError(f"ثابت مخروق: {message}")
