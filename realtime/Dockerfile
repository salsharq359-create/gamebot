FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY realtime ./realtime
RUN useradd --create-home appuser
USER appuser
EXPOSE 3001
CMD ["uvicorn", "realtime.server:app", "--host", "0.0.0.0", "--port", "3001"]
