FROM python:3.12-slim

WORKDIR /app
COPY webui/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY webui/ .
ENV AGENT_ENVIRONMENT_URL=http://agent_environment:8080
EXPOSE 8081
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]
