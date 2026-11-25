FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    ALFWORLD_DATA=/data/alfworld \
    AAGENT_API_URL=http://agent_environment:8080
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libffi-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY . ./
ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
