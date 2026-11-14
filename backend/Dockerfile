FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN DJANGO_DEBUG=1 python manage.py collectstatic --noinput
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
EXPOSE 8000
# ترحيل قاعدة البيانات ثم تشغيل الخادم بـ gunicorn
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn gamebot_api.wsgi:application --bind 0.0.0.0:8000 --workers 3"]
