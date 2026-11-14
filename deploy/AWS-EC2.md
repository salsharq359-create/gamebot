# نشر جيم بوت (بايثون) على AWS EC2

كل الأجزاء تعمل على خادم EC2 واحد عبر Docker، وخلفها Nginx مع HTTPS:

```
المتصفح ──HTTPS──► app.example.com ──► واجهة Flet (بايثون، :8550)
                                          │  (داخل الخادم)
تطبيق الجوال/الكمبيوتر ──HTTPS──► api.example.com ──► Django :8000 ──► PostgreSQL
                                          └──► python-socketio :3001 (Socket.io)
```

## 1. إنشاء خادم EC2

1. EC2 ← Launch instance. النظام Ubuntu 24.04 LTS، والحجم t3.small أو أكبر.
2. Security group: المنفذ 22 من جهازك فقط، و 80 و 443 للجميع. لا تفتح 8000 أو 3001 أو 8550 أو 5432.
3. اربط Elastic IP، وأضف سجلي DNS من نوع A: `api.example.com` و `app.example.com`.

## 2. تثبيت Docker ورفع المشروع

```bash
ssh ubuntu@api.example.com
sudo apt update && sudo apt install -y docker.io docker-compose-v2 certbot git
sudo usermod -aG docker ubuntu && newgrp docker
git clone <رابط مستودعك> gamebot-py && cd gamebot-py/deploy
cp .env.example .env && nano .env
```

لتوليد قيم عشوائية: `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`

## 3. شهادات HTTPS

```bash
sudo mkdir -p /var/www/certbot
sudo certbot certonly --standalone -d api.example.com
sudo certbot certonly --standalone -d app.example.com
```

ثم غيّر `example.com` في `nginx.conf` إلى نطاقك.

## 4. التشغيل

```bash
docker compose up -d --build
docker compose exec backend python manage.py createsuperuser    # لوحة الإدارة: https://api.example.com/admin/
curl https://api.example.com/api/health/
```

افتح `https://app.example.com` لاستخدام التطبيق من المتصفح.

## 5. نسخة سطح المكتب أو الجوال

نسخة الكمبيوتر تتصل بالخوادم المنشورة مباشرة:

```bash
cd app
API_URL=https://api.example.com REALTIME_URL=https://api.example.com python main.py
```

لبناء تطبيق أندرويد: `flet build apk` (يحتاج Flutter SDK على جهازك). انظر README.

## ملاحظة عن Firebase Hosting

Firebase Hosting يستضيف ملفات ثابتة فقط، وواجهة Flet هنا تعمل كخادم بايثون (لأنها تتصل بـ Django و Socket.io من
الخادم). لذلك تُنشر الواجهة على EC2. يمكنك استخدام Firebase Hosting لصفحة تعريفية بالمشروع.
