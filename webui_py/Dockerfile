FROM python:3.12-slim

WORKDIR /app

COPY webui_py/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY webui_py/ .
COPY agent/process_creation.py agent/process_repository.py agent/workflow_parser.py agent/workflow_validator.py agent/workflow_contract.py agent/workflow_structs.py agent/workflow_nodes.py agent/workflow_2_0.schema.json /opt/agent-runtime/
ENV AGENT_RUNTIME_PATH=/opt/agent-runtime
