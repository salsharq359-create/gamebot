# صورة Render: Django + خادم الروبوت معاً (انظر combined.py). تُبنى من جذر المستودع (dockerContext: .)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY backend/requirements.txt backend-requirements.txt
COPY realtime/requirements.txt realtime-requirements.txt
RUN pip install --no-cache-dir -r backend-requirements.txt -r realtime-requirements.txt
COPY backend ./backend
COPY realtime/realtime ./backend/realtime
COPY deploy/render/combined.py ./backend/combined.py
WORKDIR /srv/backend
RUN DJANGO_DEBUG=1 python manage.py collectstatic --noinput
RUN useradd --create-home appuser && chown -R appuser /srv
USER appuser
# Render يحدد المنفذ في PORT. نرحّل قاعدة البيانات ثم نشغّل الخادمين معاً.
CMD ["sh", "-c", "python manage.py migrate --noinput && DJANGO_URL=http://127.0.0.1:${PORT:-10000} exec uvicorn combined:app --host 0.0.0.0 --port ${PORT:-10000}"]
