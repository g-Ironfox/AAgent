FROM python:3.12-slim

WORKDIR /app

COPY webui_py/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY webui_py/main.py ./
COPY webui/static ./static

EXPOSE 8081
