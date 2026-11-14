-- استعلامات TM351 على قاعدة جيم بوت (PostgreSQL 16). كل الأوقات بتوقيت الكويت.
-- التشغيل:  python -m analytics.sqlrun   (أو انسخها في psql)

-- name: q1_daily_earnings_by_game
-- الأرباح اليومية لكل لعبة تجريبية (GROUP BY على تاريخ محلي + JOIN)
SELECT (e.created_at AT TIME ZONE 'Asia/Kuwait')::date AS day,
       p.key                                           AS game,
       COUNT(*)                                        AS records,
       ROUND(SUM(e.cents) / 100.0, 2)                  AS dollars
FROM core_earningrecord e
JOIN core_gameplatform p ON p.id = e.platform_id
WHERE p.is_demo
GROUP BY day, game
ORDER BY day, game;

-- name: q2_top_earners_window
-- ترتيب المستخدمين بدالة نافذة (RANK) — للوحة المتصدرين، فقط من وافق على الظهور
SELECT u.id, ROUND(SUM(e.cents) / 100.0, 2) AS dollars,
       RANK() OVER (ORDER BY SUM(e.cents) DESC) AS rank
FROM core_earningrecord e
JOIN auth_user u    ON u.id = e.user_id
JOIN core_profile pr ON pr.user_id = u.id AND pr.leaderboard
GROUP BY u.id
ORDER BY rank
LIMIT 10;

-- name: q3_minutes_vs_limit
-- دقائق اللعب لكل مستخدم في كل يوم مقارنة بحده اليومي (JOIN + CASE)
SELECT s.user_id,
       (s.started_at AT TIME ZONE 'Asia/Kuwait')::date AS day,
       ROUND(SUM(s.seconds) / 60.0, 1)                AS minutes,
       pr.daily_limit_min,
       CASE WHEN pr.daily_limit_min > 0 AND SUM(s.seconds) / 60.0 >= pr.daily_limit_min
            THEN 1 ELSE 0 END                          AS over_limit
FROM core_playsession s
JOIN core_profile pr ON pr.user_id = s.user_id
GROUP BY s.user_id, day, pr.daily_limit_min
ORDER BY minutes DESC
LIMIT 10;

-- name: q4_duplicate_sessions
-- جودة البيانات: جلسات مسجلة أكثر من مرة (GROUP BY ... HAVING)
SELECT user_id, started_at, COUNT(*) AS copies
FROM core_playsession
GROUP BY user_id, started_at
HAVING COUNT(*) > 1
ORDER BY copies DESC, started_at;

-- name: q5_offline_share_by_hour
-- نسبة الأرباح التي جاءت من العمل بدون اتصال حسب ساعة اليوم
SELECT EXTRACT(HOUR FROM e.created_at AT TIME ZONE 'Asia/Kuwait')::int AS hour,
       COUNT(*)                                                         AS records,
       ROUND(100.0 * AVG(CASE WHEN e.client_id LIKE 'off-%' THEN 1 ELSE 0 END), 1) AS offline_pct
FROM core_earningrecord e
WHERE e.source = 'bot'
GROUP BY hour
ORDER BY hour;

-- name: q6_custom_platform_names
-- أسماء المنصات الخاصة كما كتبها المستخدمون (قبل التوحيد)
SELECT name, COUNT(*) AS platforms
FROM core_gameplatform
WHERE NOT is_demo
GROUP BY name
ORDER BY platforms DESC, name;
