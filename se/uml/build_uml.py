"""
TM354: رسوم UML لجيم بوت بالعربية والإنجليزية (PlantUML).

  python se/uml/build_uml.py            يكتب ملفات .puml في se/uml/src/{ar,en}
  python se/uml/build_uml.py --render   ويرسمها PNG في se/uml/png/{ar,en} (يحتاج PlantUML، انظر PLANTUML_CMD)

رسم آلة الحالات يُولَّد من جدول TRANSITIONS في realtime/realtime/bot.py نفسه، فلا يمكن أن يختلف الرسم عن الكود.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "realtime"))
from realtime.bot import TERMINAL, TRANSITIONS, State  # noqa: E402

STYLE = """skinparam dpi 150
skinparam defaultFontName Cairo
skinparam defaultFontSize 13
skinparam shadowing false
skinparam roundCorner 10
skinparam ArrowColor #141B3D
skinparam ActorBorderColor #141B3D
skinparam UsecaseBorderColor #141B3D
skinparam UsecaseBackgroundColor #F4F7FF
skinparam ClassBorderColor #141B3D
skinparam ClassBackgroundColor #F8FAFF
skinparam ClassHeaderBackgroundColor #E8EEFF
skinparam StateBorderColor #141B3D
skinparam StateBackgroundColor #F4F7FF
skinparam ActivityBorderColor #141B3D
skinparam ActivityBackgroundColor #F4F7FF
skinparam ActivityDiamondBackgroundColor #FFF6D6
skinparam ParticipantBorderColor #141B3D
skinparam ParticipantBackgroundColor #F4F7FF
skinparam SequenceLifeLineBorderColor #8A93B5
skinparam NoteBackgroundColor #FFF8E1
skinparam NoteBorderColor #E0B84C
skinparam PackageBorderColor #141B3D
skinparam NodeBorderColor #141B3D
skinparam NodeBackgroundColor #F8FAFF
skinparam ComponentBorderColor #141B3D
skinparam ComponentBackgroundColor #EEF3FF
skinparam DatabaseBorderColor #141B3D
skinparam linetype ortho
"""


def T(ar: str, en: str):
    return {"ar": ar, "en": en}


def L(x, lang):
    return x[lang] if isinstance(x, dict) else x


# --------------------------------------------------------------- 1) حالات الاستخدام
def use_cases(lang):
    t = lambda a, e: L(T(a, e), lang)  # noqa: E731
    return f"""@startuml
{STYLE}
skinparam linetype polyline
actor "{t('اللاعب', 'Player')}" as P
actor "{t('خادم الروبوت', 'Bot server')}" as RS <<system>>
rectangle "{t('جيم بوت', 'GameBot')}" {{
  usecase "{t('إنشاء حساب / دخول', 'Register / log in')}" as UC1
  usecase "{t('ربط الألعاب', 'Link games')}" as UC2
  usecase "{t('طلب خطة من المستشار', 'Ask the advisor for a plan')}" as UC3
  usecase "{t('تشغيل الروبوت', 'Run the robot')}" as UC4
  usecase "{t('إيقاف الروبوت', 'Stop the robot')}" as UC5
  usecase "{t('اللعب على الجهاز بدون اتصال', 'Play offline on the device')}" as UC6
  usecase "{t('مزامنة النتائج', 'Sync offline results')}" as UC7
  usecase "{t('عرض الأرباح والتحليلات', 'View earnings and analytics')}" as UC8
  usecase "{t('طلب سحب (محاكاة)', 'Request a withdrawal (simulated)')}" as UC9
  usecase "{t('إضافة منصة وربح يدوي', 'Add a platform and a manual earning')}" as UC10
  usecase "{t('تصدير بياناتي / حذف حسابي', 'Export my data / delete my account')}" as UC11
  usecase "{t('التحقق من الهوية', 'Authenticate')}" as AUTH
}}
P -right-> UC1
P -right-> UC2
P -right-> UC3
P -right-> UC4
P -right-> UC5
P -right-> UC8
P -right-> UC9
P -right-> UC10
P -right-> UC11
UC1 -[hidden]down- UC2
UC2 -[hidden]down- UC3
UC3 -[hidden]down- UC4
UC4 -[hidden]down- UC5
UC5 -[hidden]down- UC8
UC8 -[hidden]down- UC9
UC9 -[hidden]down- UC10
UC10 -[hidden]down- UC11
UC4 -[hidden]right- UC6
UC6 -[hidden]down- UC7
UC7 -[hidden]down- AUTH
UC4 ..> AUTH : <<include>>
UC9 ..> AUTH : <<include>>
UC6 ..> UC4 : <<extend>>\\n[{t('لا يوجد اتصال', 'no connection')}]
UC7 ..> AUTH : <<include>>
UC6 ..> UC7 : <<precedes>>
UC6 -right- RS
note right of UC7
  {t('النتائج تُحفظ مشفّرة على الجهاز', 'Results are stored encrypted on the device')}
  {t('والخادم يتحقق من كل سجل عند المزامنة', 'and the server checks every record on sync')}
end note
@enduml
"""


# ---------------------------------------------------------- 2) نموذج المجال (الجداول)
def domain(lang):
    t = lambda a, e: L(T(a, e), lang)  # noqa: E731
    return f"""@startuml
{STYLE}
hide circle
hide methods
skinparam linetype polyline
class User {{
  username
  password (PBKDF2)
}}
class Profile {{
  failed_attempts : int
  locked_until : datetime
  daily_limit_min : 0..240
  leaderboard : bool
}}
class GamePlatform {{
  key {{unique per owner}}
  name
  is_demo : bool
}}
class UserGameAccount {{
  linked : bool
}}
class GameTask {{
  key
  reward_cents > 0
  minutes > 0
  max_per_day
}}
class EarningRecord {{
  cents
  source : bot | manual
  client_id {{unique per user}}
  created_at
}}
class Withdrawal {{
  method
  cents > 0
}}
class PlaySession {{
  started_at {{unique per user}}
  seconds
}}
class BotStrategy {{
  minutes_budget
  expected_cents
  plan : JSON
}}
class Notification
class SecurityEvent
User "1" -left- "1" Profile
User "1" -down- "0..*" UserGameAccount
UserGameAccount "0..*" -down- "1" GamePlatform
GamePlatform "1" *-down- "1..*" GameTask
User "0..1" -- "0..*" GamePlatform : {t('يملك (منصة خاصة)', 'owns (custom)')}
User "1" -down- "0..*" EarningRecord
EarningRecord "0..*" -down-> "0..1" GameTask
User "1" -down- "0..*" Withdrawal
User "1" -right- "0..*" PlaySession
User "1" -right- "0..*" BotStrategy
User "1" -up- "0..*" Notification
User "1" -up- "0..*" SecurityEvent
PlaySession -[hidden]down- BotStrategy
Profile -[hidden]down- Notification
note bottom of Withdrawal
  <b>{t('ثابت', 'Invariant')}</b> (OCL)
  context User inv BalanceNeverNegative:
    self.earnings.cents->sum() - self.withdrawals.cents->sum() >= 0
end note
note right of EarningRecord
  context EarningRecord inv:
    self.source = 'bot' implies
      self.cents = self.task.reward_cents
  {t('(المبلغ من جدول المهام، لا من العميل)', '(amount comes from the task table, never the client)')}
end note
@enduml
"""


# ------------------------------------------------ 3) تصميم محرك الروبوت (الأنماط)
def engine(lang):
    t = lambda a, e: L(T(a, e), lang)  # noqa: E731
    return f"""@startuml
{STYLE}
skinparam linetype polyline
interface Game <<Protocol>> {{
  +play_round() : Iterator[dict]
}}
class CoinCollector {{
  +plan() : (order, best, greedy)
  -_distances(start)
}}
class NumberGuess
class TicTacToe {{
  -_minimax(board, player) <<lru_cache>>
}}
Game <|.. CoinCollector
Game <|.. NumberGuess
Game <|.. TicTacToe
class "games" as F <<module>> {{
  FACTORIES : dict[str, type]
  +new_game(key, rng) : Game
}}
F ..> Game : <<create>>
class "bot" as B <<module>> {{
  +run_session(games, rounds, tasks, rng, stopped) : Iterator[dict]
  -_schedule() / _play_round() / _streak_bonus()
}}
B ..> F : new_game()
enum State {{
  IDLE
  RUNNING
  STOPPING
  FINISHED
  STOPPED
  INTERRUPTED
  FAILED
}}
class BotSession {{
  +state : State
  +local : bool
  +history
  +fire(event) : State
  +can(event) : bool
  +start(local=False)
  +active : bool
  +stop_requested : bool
}}
BotSession --> State
BotSession ..> "TRANSITIONS" : {t('يقرأ', 'reads')}
class "server (python-socketio)" as S <<module>>
class GameBotApp <<Flet>>
S --> "0..*" BotSession : running[user_id]
GameBotApp --> "1" BotSession : session
S ..> B
GameBotApp ..> B : {t('بدون اتصال', 'offline')}
note top of Game
  <b>Strategy</b>
  {t('الجلسة لا تعرف أي لعبة تلعب', 'the session does not know which game it plays')}
end note
note bottom of F
  <b>Factory</b>
  {t('لعبة جديدة = صنف + سطر واحد', 'a new game = one class + one line')}
end note
note bottom of BotSession
  <b>State</b>
  {t('جدول انتقالات', 'table-driven')}
  {t('انتقال غير موجود في الجدول يرفع IllegalTransition', 'a transition not in the table raises IllegalTransition')}
end note
@enduml
"""


# --------------------------------------------- 4) قواعد المزامنة (سلسلة المسؤولية)
def rules(lang):
    t = lambda a, e: L(T(a, e), lang)  # noqa: E731
    return f"""@startuml
{STYLE}
skinparam linetype polyline
abstract class Rule {{
  +reason : str
  +check(c : Candidate, ctx : SyncContext) : str | None
}}
class WellFormed
class ValidSignature
class PlayedRecently
class KnownDemoTask
class GameLinked
class NotDuplicate
class WithinDailyLimit
Rule <|-- WellFormed
Rule <|-- ValidSignature
Rule <|-- PlayedRecently
Rule <|-- KnownDemoTask
Rule <|-- GameLinked
Rule <|-- NotDuplicate
Rule <|-- WithinDailyLimit
class SyncContext <<dataclass>> {{
  user
  key : str
  linked : set
  now : datetime
}}
class Candidate <<dataclass>> {{
  raw : dict
  client_id : str
  played : datetime
  task : GameTask
}}
class "sync_rules" as M <<module>> {{
  RULES : tuple[Rule, ...]
  +first_failure(c, ctx) : str | None
}}
M o-- "7" Rule : {t('بالترتيب', 'ordered')}
Rule ..> Candidate
Rule ..> SyncContext
class "views.offline_sync" as V <<function>>
V ..> M : first_failure()
note right of M
  <b>Chain of Responsibility</b>
  {t('كل قاعدة ترجع None (مقبول) أو سبب الرفض.', 'each rule returns None (accepted) or a reason.')}
  {t('السلسلة تتوقف عند أول رفض.', 'the chain stops at the first rejection.')}
  {t('قاعدة جديدة = صنف جديد في RULES فقط', 'a new rule = one new class in RULES')}
  {t('(مفتوح للتوسعة، مغلق للتعديل)', '(open for extension, closed for modification)')}
end note
@enduml
"""


# ------------------------------------------------- 5) تسلسل: جلسة روبوت متصلة
def seq_session(lang):
    t = lambda a, e: L(T(a, e), lang)  # noqa: E731
    return f"""@startuml
{STYLE}
skinparam linetype polyline
autonumber
actor "{t('اللاعب', 'Player')}" as P
participant "{t('التطبيق', 'App')}\\n(Flet)" as A
participant "{t('خادم الروبوت', 'Bot server')}\\n(socketio)" as R
participant "run_session\\n+ Game" as G
participant "Django\\nREST" as D
database PostgreSQL as DB
P -> A : {t('تشغيل الروبوت', 'Run robot')}
A -> R : start_bot(rounds, tasks, delta)
R -> D : GET /api/user/accounts/
D --> R : {t('الألعاب المرتبطة', 'linked games')}
R -> R : BotSession.start()
R --> A : ok
R ->> A : bot_started
loop {t('لكل حدث من الجلسة', 'for each session event')}
  R -> G : next()
  G --> R : move / log / task
  alt task
    R -> D : POST /api/internal/earnings/
    D -> DB : SELECT … FOR UPDATE ({t('قفل المستخدم', 'lock user')})
    D -> DB : {t('عدّ مهام اليوم ثم الإنشاء', 'count today, then insert')}
    D --> R : accepted, cents
    R ->> A : earning
  else move
    R ->> A : bot_event ({t('إطار فروق', 'delta frame')})
  end
  opt {t('طلب الإيقاف', 'stop requested')}
    P -> A : {t('إيقاف', 'Stop')}
    A -> R : stop_bot
    R -> R : BotSession.fire("stop")
  end
end
R -> R : BotSession.fire("done")
R -> D : POST /api/internal/sessions/
R ->> A : bot_done(outcome)
A -> A : session.fire("done")
@enduml
"""


# ---------------------------------------- 6) تسلسل: المزامنة مع CRC وإعادة الإرسال
def seq_sync(lang):
    t = lambda a, e: L(T(a, e), lang)  # noqa: E731
    return f"""@startuml
{STYLE}
autonumber
participant "OfflineQueue\\n({t('الجهاز', 'device')})" as Q
participant "views.offline_sync" as V
participant "sync_rules\\nRULES" as RU
database PostgreSQL as DB
Q -> Q : build_payload()\\nDEFLATE + CRC-32
loop {t('حتى 3 مرات (ARQ)', 'up to 3 times (ARQ)')}
  Q -> V : POST offline-sync\\nX-Payload-CRC32
  alt {t('CRC لا يطابق', 'CRC mismatch')}
    V --> Q : 400 crc_failed
  else {t('سليم', 'intact')}
    V -> V : {t('فك الضغط (حد 2MB)', 'inflate (2 MB cap)')}
    V -> DB : SELECT … FOR UPDATE
    loop {t('لكل سجل', 'for each record')}
      V -> RU : first_failure(candidate, ctx)
      RU --> V : None | reason
      opt None
        V -> DB : INSERT EarningRecord\\n({t('المبلغ من جدول المهام', 'amount from task table')})
      end
    end
    V --> Q : accepted, duplicates,\\nrejected, reasons{{}}
  end
end
Q -> Q : {t('حذف السجلات المعالجة', 'drop processed records')}
@enduml
"""


# --------------------------------------------- 7) آلة الحالات (من الكود مباشرة)
STATE_AR = {"IDLE": "خامل", "RUNNING": "يعمل", "STOPPING": "يتوقف", "FINISHED": "انتهى", "STOPPED": "أُوقف",
            "INTERRUPTED": "انقطع", "FAILED": "فشل"}
EVENT_AR = {"start": "تشغيل", "stop": "إيقاف", "done": "انتهى الجدول", "connection_lost": "انقطاع الاتصال",
            "error": "خطأ", "reset": "جلسة جديدة"}


def state_machine(lang):
    def name(s):
        return f"{STATE_AR[s.name]}\\n{s.value}" if lang == "ar" else s.value
    lines = ["@startuml", STYLE, "skinparam linetype polyline", "hide empty description"]
    for s in State:
        lines.append(f'state "{name(s)}" as {s.name}' + (" #E8FFD0" if s in TERMINAL else ""))
    lines.append("[*] --> IDLE")
    resets = []
    for (src, ev), dst in TRANSITIONS.items():
        if ev == "reset":
            resets.append(src)
            continue
        label = f"{EVENT_AR[ev]} ({ev})" if lang == "ar" else ev
        lines.append(f"{src.name} --> {dst.name} : {label}")
    reset = f"{EVENT_AR['reset']} (reset)" if lang == "ar" else "reset"
    for src in resets:
        lines.append(f"{src.name} -[#8A93B5,dashed]-> IDLE : {reset}")
    note = ("يُولَّد هذا الرسم من جدول TRANSITIONS في bot.py:\\n13 انتقالاً مسموحاً، وأي انتقال آخر يرفع IllegalTransition"
            if lang == "ar" else
            "Generated from the TRANSITIONS table in bot.py:\\n13 allowed transitions; any other raises IllegalTransition")
    lines += [f"note right of RUNNING : {note}", "@enduml"]
    return "\n".join(lines)


# ----------------------------------------------- 8) نشاط: طلب سحب (بمسارات)
def activity_withdraw(lang):
    t = lambda a, e: L(T(a, e), lang)  # noqa: E731
    return f"""@startuml
{STYLE}
|{t('المستخدم', 'User')}|
start
:{t('يختار المبلغ وطريقة السحب', 'Choose amount and method')};
|{t('التطبيق', 'App')}|
:POST /api/withdrawals/;
|{t('الخادم (Django)', 'Server (Django)')}|
if ({t('طريقة معروفة؟', 'known method?')}) then ({t('لا', 'no')})
  :400;
  stop
endif
if ({t('مبلغ > 0؟', 'amount > 0?')}) then ({t('لا', 'no')})
  :400;
  stop
endif
:BEGIN;
|{t('قاعدة البيانات', 'Database')}|
:SELECT … FOR UPDATE\\n({t('قفل صف المستخدم', 'lock the user row')});
note right
  {t('أي طلب سحب آخر لنفس المستخدم', 'any other withdrawal for the same user')}
  {t('ينتظر هنا حتى COMMIT', 'waits here until COMMIT')}
end note
|{t('الخادم (Django)', 'Server (Django)')}|
if ({t('المبلغ ≤ الرصيد؟', 'amount ≤ balance?')}) then ({t('لا', 'no')})
  :ROLLBACK\\n400 {t('الرصيد غير كافٍ', 'insufficient balance')};
  stop
else ({t('نعم', 'yes')})
  |{t('قاعدة البيانات', 'Database')}|
  :INSERT Withdrawal;
  |{t('الخادم (Django)', 'Server (Django)')}|
  :check_invariant({t('الرصيد ≥ 0', 'balance ≥ 0')});
  :COMMIT;
  fork
    :{t('سجل أمني', 'security log')};
  fork again
    :{t('تنبيه', 'notification')};
  end fork
endif
|{t('التطبيق', 'App')}|
:{t('يعرض الرصيد الجديد', 'Show new balance')};
stop
@enduml
"""


# ---------------------------------------- 9) تسلسل: السباق قبل الإصلاح وبعده
def race(lang):
    t = lambda a, e: L(T(a, e), lang)  # noqa: E731
    return f"""@startuml
{STYLE}
participant "{t('طلب سحب 1', 'Request 1')}" as A
database PostgreSQL as DB
participant "{t('طلب سحب 2', 'Request 2')}" as B
== {t('قبل TM354: transaction.atomic فقط', 'Before TM354: transaction.atomic only')} ==
A -> DB : {t('الرصيد؟', 'balance?')}
B -> DB : {t('الرصيد؟', 'balance?')}
DB --> A : 5$
DB --> B : 5$
A -> DB : INSERT 5$ (OK)
B -> DB : INSERT 5$ (OK)
note over A, B #FFE0E0 : {t('الرصيد = -5$ (خرق الثابت). في الاختبار: 5 طلبات فصار الرصيد -20$', 'balance = -5$ (invariant broken). In the test: 5 requests left -20$')}
== {t('بعد TM354: SELECT … FOR UPDATE', 'After TM354: SELECT … FOR UPDATE')} ==
A -> DB : {t('قفل المستخدم', 'lock user')}
B -> DB : {t('قفل المستخدم', 'lock user')}
note right of B : {t('ينتظر', 'waits')}
A -> DB : {t('الرصيد؟ 5$ ثم INSERT 5$ ثم COMMIT', 'balance? 5$, INSERT 5$, COMMIT')}
DB --> B : {t('القفل متاح', 'lock granted')}
B -> DB : {t('الرصيد؟ 0$', 'balance? 0$')}
DB --> B : 400 {t('الرصيد غير كافٍ', 'insufficient balance')}
note over A, B #E0FFE0 : {t('ينجح طلب واحد فقط، والرصيد 0', 'exactly one succeeds; balance 0')}
@enduml
"""


# ------------------------------------------------- 10) النشر والمكوّنات
def deployment(lang):
    t = lambda a, e: L(T(a, e), lang)  # noqa: E731
    return f"""@startuml
{STYLE}
skinparam linetype polyline
node "{t('جهاز المستخدم (جوال / حاسوب)', 'User device (phone / desktop)')}" as dev {{
  component "{t('تطبيق Flet', 'Flet app')}\\n(gb.app + screens)" as app
  component "{t('محرك الألعاب (نسخة)', 'game engine (copy)')}\\nengine/" as eng
  file "{t('طابور مشفّر', 'encrypted queue')}\\nAES-256-GCM" as q
}}
node "{t('خادم سحابي', 'cloud server')} (docker compose)" as srv {{
  component nginx
  component "{t('خادم الروبوت', 'Bot server')}\\npython-socketio + uvicorn" as rt
  component "Django REST\\ncore" as dj
  database "PostgreSQL 16" as pg
}}
app --> eng
app --> q
app --> nginx : HTTPS (REST)
app --> nginx : WebSocket (Socket.IO)
nginx --> dj
nginx --> rt
rt --> dj : HTTP {t('داخلي', 'internal')}\\nX-Internal-Key
dj --> pg : SQL
@enduml
"""


# ------------------------------------------------------------- 11) الحزم
def packages(lang):
    t = lambda a, e: L(T(a, e), lang)  # noqa: E731
    return f"""@startuml
{STYLE}
skinparam linetype polyline
set separator none
package "app.gb" {{
  package "app.py" <<{t('تحكم', 'controller')}>>
  package "screens" <<{t('عرض', 'views')}>> {{
    package "course_labs"
    package "account_screens"
  }}
  package "client"
  package "offline"
  package "ui"
  package "engine"
  package "tm355"
  package "algorithms"
}}
package "realtime.realtime" {{
  package "server"
  package "bot"
  package "games"
}}
package "backend.core" {{
  package "views"
  package "sync_rules"
  package "advisor"
  package "contracts"
  package "auth"
  package "models"
}}
"app.py" ..> "course_labs"
"app.py" ..> "account_screens"
"course_labs" ..> "client"
"course_labs" ..> "ui"
"course_labs" ..> "tm355"
"course_labs" ..> "algorithms"
"account_screens" ..> "ui"
"app.py" ..> "client"
"app.py" ..> "offline"
"app.py" ..> "engine"
"offline" ..> "tm355"
"server" ..> "bot"
"bot" ..> "games"
"views" ..> "sync_rules"
"views" ..> "advisor"
"views" ..> "contracts"
"advisor" ..> "contracts"
"views" ..> "auth"
"sync_rules" ..> "models"
"views" ..> "models"
"engine" .[#B0B0B0].> "bot" : {t('نسخة مطابقة', 'identical copy')}
@enduml
"""


DIAGRAMS = {"01-use-cases": use_cases, "02-domain": domain, "03-engine": engine, "04-sync-rules": rules,
            "05-seq-session": seq_session, "06-seq-sync": seq_sync, "07-state-machine": state_machine,
            "08-activity-withdraw": activity_withdraw, "09-seq-race": race, "10-deployment": deployment,
            "11-packages": packages}


def main():
    render = "--render" in sys.argv
    cmd = shlex.split(os.environ.get("PLANTUML_CMD", "plantuml"))
    for lang in ("ar", "en"):
        src = HERE / "src" / lang
        png = HERE / "png" / lang
        src.mkdir(parents=True, exist_ok=True)
        png.mkdir(parents=True, exist_ok=True)
        for name, fn in DIAGRAMS.items():
            p = src / f"{name}.puml"
            p.write_text(fn(lang))
            if render:
                subprocess.run(cmd + [str(p), str(png / f"{name}.png")], check=True,
                               stderr=subprocess.DEVNULL)
    print(f"{len(DIAGRAMS)} رسماً × لغتين")


if __name__ == "__main__":
    main()
