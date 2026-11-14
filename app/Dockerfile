FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 FLET_WEB_PORT=8550
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "flet-web==1.0.3" "fastapi==0.115.12"
COPY . .
RUN useradd --create-home appuser
USER appuser
EXPOSE 8550
CMD ["python", "main.py"]
