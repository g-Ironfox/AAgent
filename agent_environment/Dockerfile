FROM python:3.12-slim

WORKDIR /app
COPY agent_environment/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agent_environment/ .
EXPOSE 8080
# FileStore maintains process-local state; use a single worker and replica.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
