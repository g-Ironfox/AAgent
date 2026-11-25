FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 ALFWORLD_DATA=/data/alfworld AAGENT_API_URL=http://agent_environment:8080
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libffi-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY alfworld_runner/requirements.txt alfworld_runner/requirements.txt
COPY benchmark_common/requirements.txt benchmark_common/requirements.txt
COPY benchmark_worker/requirements.txt benchmark_worker/requirements.txt
RUN pip install -r benchmark_worker/requirements.txt
COPY alfworld_runner/*.py alfworld_runner/config.yaml alfworld_runner/
COPY benchmark_common/*.py benchmark_common/
COPY benchmark_worker/*.py benchmark_worker/
ENTRYPOINT ["python", "-m", "benchmark_worker.main"]
CMD ["work"]
