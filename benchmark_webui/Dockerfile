FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY benchmark_common/requirements.txt benchmark_common/requirements.txt
COPY benchmark_webui/requirements.txt benchmark_webui/requirements.txt
RUN pip install -r benchmark_webui/requirements.txt
COPY benchmark_common/*.py benchmark_common/
COPY benchmark_webui/*.py benchmark_webui/
COPY benchmark_webui/static benchmark_webui/static
EXPOSE 8085
CMD ["uvicorn", "benchmark_webui.main:app", "--host", "0.0.0.0", "--port", "8085"]
