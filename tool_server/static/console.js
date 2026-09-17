import { createAutoRefresh } from "./auto-refresh.js";

const state = {
  data: null,
  status: "all",
  query: "",
  selectedTool: null,
  selectedTaskId: null,
};

const elements = Object.fromEntries([
  "connectionState", "searchInput", "lastRefresh", "refreshState", "interval", "pauseButton", "refreshButton", "providerCount", "toolCount",
  "workingCount", "failedCount", "notice", "providerBadge", "providerList", "toolBadge",
  "toolList", "taskBadge", "taskList", "invokeDialog", "invokeForm", "invokeTitle", "argumentsInput",
  "inputSchemaView", "outputSchemaView",
  "modeInput", "timeoutInput", "callbackInput", "callbackOptions", "callbackQueueInput", "callbackEventTypeInput",
  "callbackWorkingInput", "callbackCompletedInput", "callbackFailedInput", "invokeError", "taskDialog", "detailTitle", "taskDetailBody",
].map((id) => [id, document.getElementById(id)]));

const statusNames = {
  pending: "等待中",
  working: "执行中",
  completed: "已完成",
  failed: "失败",
};

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const error = new Error(payload.detail || payload.error || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function setConnection(kind, label) {
  elements.connectionState.className = `connection-state ${kind}`;
  elements.connectionState.querySelector("span").textContent = label;
}

function showNotice(message) {
  elements.notice.textContent = message;
  elements.notice.hidden = !message;
}

function emptyNode() {
  return document.getElementById("emptyTemplate").content.cloneNode(true);
}

function includesQuery(...values) {
  if (!state.query) return true;
  return values.some((value) => String(value || "").toLowerCase().includes(state.query));
}

function schemaExample(schema) {
  if (!schema || typeof schema !== "object") return null;
  if (schema.default !== undefined) return schema.default;
  if (schema.example !== undefined) return schema.example;
  if (schema.type === "object" || schema.properties) {
    return Object.fromEntries(Object.entries(schema.properties || {}).map(([key, value]) => [key, schemaExample(value)]));
  }
  if (schema.type === "array") return [];
  if (schema.type === "boolean") return false;
  if (schema.type === "integer" || schema.type === "number") return 0;
  return "";
}

function schemaType(schema) {
  if (!schema || typeof schema !== "object") return "unknown";
  if (Array.isArray(schema.type)) return schema.type.join(" | ");
  if (schema.type) return schema.type;
  if (schema.properties) return "object";
  if (schema.items) return "array";
  if (schema.const !== undefined) return "const";
  return "any";
}

function schemaConstraint(schema) {
  const parts = [];
  if (Array.isArray(schema.enum)) parts.push(`enum: ${schema.enum.map((value) => JSON.stringify(value)).join(", ")}`);
  if (schema.const !== undefined) parts.push(`const: ${JSON.stringify(schema.const)}`);
  if (schema.default !== undefined) parts.push(`default: ${JSON.stringify(schema.default)}`);
  if (schema.format) parts.push(`format: ${schema.format}`);
  if (schema.pattern) parts.push(`pattern: ${schema.pattern}`);
  if (schema.minimum !== undefined) parts.push(`min: ${schema.minimum}`);
  if (schema.maximum !== undefined) parts.push(`max: ${schema.maximum}`);
  if (schema.minLength !== undefined) parts.push(`minLength: ${schema.minLength}`);
  if (schema.maxLength !== undefined) parts.push(`maxLength: ${schema.maxLength}`);
  return parts.join(" · ");
}

function createSchemaNode(name, schema, required = false, depth = 0) {
  const item = document.createElement("li");
  item.className = "schema-node";
  item.style.setProperty("--schema-depth", depth);

  const row = document.createElement("div");
  row.className = "schema-row";

  const key = document.createElement("code");
  key.className = "schema-key";
  key.textContent = name;
  row.append(key);

  const type = document.createElement("span");
  type.className = "schema-type";
  type.textContent = schemaType(schema);
  row.append(type);

  if (required) {
    const badge = document.createElement("span");
    badge.className = "schema-required";
    badge.textContent = "必填";
    row.append(badge);
  }
  item.append(row);

  if (schema.description) {
    const description = document.createElement("p");
    description.className = "schema-description";
    description.textContent = schema.description;
    item.append(description);
  }

  const constraintText = schemaConstraint(schema);
  if (constraintText) {
    const constraints = document.createElement("p");
    constraints.className = "schema-constraints";
    constraints.textContent = constraintText;
    item.append(constraints);
  }

  const children = document.createElement("ul");
  const requiredProperties = new Set(schema.required || []);
  for (const [propertyName, propertySchema] of Object.entries(schema.properties || {})) {
    children.append(createSchemaNode(propertyName, propertySchema, requiredProperties.has(propertyName), depth + 1));
  }
  if (schema.items && typeof schema.items === "object") {
    children.append(createSchemaNode("items[]", schema.items, false, depth + 1));
  }
  if (children.childElementCount) item.append(children);
  return item;
}

function renderSchema(container, schema, rootName) {
  container.replaceChildren();
  if (!schema || typeof schema !== "object") {
    const empty = document.createElement("p");
    empty.className = "schema-empty";
    empty.textContent = "未声明 Schema";
    container.append(empty);
    return;
  }
  const tree = document.createElement("ul");
  tree.className = "schema-tree";
  tree.append(createSchemaNode(rootName, schema));
  container.append(tree);
}

function formatTime(value, includeDate = false) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return new Intl.DateTimeFormat("zh-CN", includeDate
    ? { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }
    : { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(date);
}

function renderSummary() {
  const summary = state.data.summary;
  elements.providerCount.textContent = summary.providers;
  elements.toolCount.textContent = summary.tools;
  elements.workingCount.textContent = summary.statuses.working;
  elements.failedCount.textContent = summary.statuses.failed;
  elements.lastRefresh.textContent = formatTime(state.data.fetched_at);
  elements.lastRefresh.classList.remove("sync-error");
}

function renderProviders() {
  const providers = state.data.providers.filter((provider) => includesQuery(provider.provider_id, ...provider.tools));
  elements.providerBadge.textContent = providers.length;
  elements.providerList.replaceChildren();
  if (!providers.length) return elements.providerList.append(emptyNode());
  for (const provider of providers) {
    const item = document.createElement("article");
    item.className = "provider-item";
    const names = provider.tools.map((name) => `<span>${escapeHtml(name)}</span>`).join("");
    item.innerHTML = `<div class="provider-name"><i></i><strong>${escapeHtml(provider.provider_id)}</strong></div>
      <div class="provider-meta"><span>revision ${provider.revision}</span><span>${provider.queued_messages} queued</span></div>
      <div class="provider-tools">${names}</div>`;
    elements.providerList.append(item);
  }
}

function renderTools() {
  const tools = state.data.tools.filter((tool) => includesQuery(tool.name, tool.description, tool.provider_id));
  elements.toolBadge.textContent = tools.length;
  elements.toolList.replaceChildren();
  if (!tools.length) return elements.toolList.append(emptyNode());
  for (const tool of tools) {
    const item = document.createElement("article");
    item.className = "tool-item";
    item.innerHTML = `<div class="tool-main"><strong>${escapeHtml(tool.name)}</strong><small>${escapeHtml(tool.description || "无描述")}</small></div>
      <span class="tool-provider">${escapeHtml(tool.provider_id)}</span><span class="revision">r${tool.revision}</span>
      <button class="invoke-button" type="button" title="调用 ${escapeHtml(tool.name)}" aria-label="调用 ${escapeHtml(tool.name)}"><svg viewBox="0 0 24 24"><path d="m5 12 14-7-4 14-3-6-7-1Z"></path></svg></button>`;
    item.querySelector("button").addEventListener("click", () => openInvoke(tool));
    elements.toolList.append(item);
  }
}

function visibleTasks() {
  return state.data.tasks.filter((task) => {
    const statusMatch = state.status === "all" || task.status === state.status;
    return statusMatch && includesQuery(task.task_id, task.tool, task.provider_id, task.status);
  });
}

function renderTasks() {
  const tasks = visibleTasks();
  elements.taskBadge.textContent = tasks.length;
  elements.taskList.replaceChildren();
  if (!tasks.length) return elements.taskList.append(emptyNode());
  for (const task of tasks) {
    const item = document.createElement("article");
    item.className = "task-item";
    item.tabIndex = 0;
    item.innerHTML = `<i class="status-dot ${task.status}"></i><div class="task-name"><strong>${escapeHtml(task.tool)}</strong><small>${escapeHtml(task.task_id.slice(0, 12))}</small></div>
      <span class="status-label ${task.status}">${statusNames[task.status] || escapeHtml(task.status)}</span><time class="task-time">${formatTime(task.updated_at)}</time>`;
    item.addEventListener("click", () => openTask(task.task_id));
    item.addEventListener("keydown", (event) => { if (event.key === "Enter") openTask(task.task_id); });
    elements.taskList.append(item);
  }
}

function render() {
  renderSummary();
  renderProviders();
  renderTools();
  renderTasks();
}

async function refresh() {
  elements.refreshButton.disabled = true;
  try {
    state.data = await request("/api/overview?limit=100");
    showNotice("");
    setConnection("online", "服务在线");
    render();
    if (elements.taskDialog.open && state.selectedTaskId) renderTaskDetail(await request(`/api/tasks/${state.selectedTaskId}`));
  } catch (error) {
    setConnection("error", "连接异常");
    elements.lastRefresh.classList.add("sync-error");
    elements.lastRefresh.textContent = "同步失败";
    showNotice(`无法读取 Tool Server：${error.message}`);
  } finally {
    elements.refreshButton.disabled = false;
    autoRefresh.schedule();
  }
}

function openInvoke(tool) {
  state.selectedTool = tool;
  elements.invokeTitle.textContent = tool.name;
  elements.argumentsInput.value = JSON.stringify(schemaExample(tool.inputSchema), null, 2);
  renderSchema(elements.inputSchemaView, tool.inputSchema, "input");
  renderSchema(elements.outputSchemaView, tool.outputSchema, "output");
  elements.callbackInput.checked = false;
  elements.callbackOptions.hidden = true;
  elements.callbackQueueInput.value = "main_agent_queue";
  elements.callbackEventTypeInput.value = "async_result";
  elements.callbackWorkingInput.checked = true;
  elements.callbackCompletedInput.checked = true;
  elements.callbackFailedInput.checked = true;
  elements.invokeError.hidden = true;
  elements.invokeDialog.showModal();
}

function renderTaskDetail(task) {
  elements.detailTitle.textContent = task.tool;
  const details = [
    ["task_id", task.task_id], ["status", statusNames[task.status] || task.status], ["provider", task.provider_id || "未派发"],
    ["created_at", formatTime(task.created_at, true)], ["updated_at", formatTime(task.updated_at, true)],
  ];
  const list = details.map(([key, value]) => `<dt>${key}</dt><dd>${escapeHtml(value)}</dd>`).join("");
  const payload = task.result !== null ? task.result : task.error;
  elements.taskDetailBody.innerHTML = `<dl class="detail-grid">${list}</dl><pre class="json-block">${escapeHtml(JSON.stringify(payload, null, 2) || "暂无结果")}</pre>`;
}

async function openTask(taskId) {
  state.selectedTaskId = taskId;
  try {
    renderTaskDetail(await request(`/api/tasks/${taskId}`));
    elements.taskDialog.showModal();
  } catch (error) {
    showNotice(`读取任务失败：${error.message}`);
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[character]);
}

elements.invokeForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.invokeError.hidden = true;
  try {
    const argumentsValue = JSON.parse(elements.argumentsInput.value);
    let callback = null;
    if (elements.callbackInput.checked) {
      const on = [
        elements.callbackWorkingInput,
        elements.callbackCompletedInput,
        elements.callbackFailedInput,
      ].filter((input) => input.checked).map((input) => input.value);
      if (!on.length) throw new Error("至少选择一个回调终态。");
      callback = {
        type: "redis",
        queue: elements.callbackQueueInput.value.trim(),
        event_type: elements.callbackEventTypeInput.value.trim(),
        on,
      };
    }
    const task = await request(`/api/tools/${encodeURIComponent(state.selectedTool.name)}/calls`, {
      method: "POST",
      body: JSON.stringify({ arguments: argumentsValue, mode: elements.modeInput.value, timeout_ms: Number(elements.timeoutInput.value), callback }),
    });
    elements.invokeDialog.close();
    await refresh();
    await openTask(task.task_id);
  } catch (error) {
    elements.invokeError.textContent = error instanceof SyntaxError ? "参数不是有效的 JSON。" : error.message;
    elements.invokeError.hidden = false;
  }
});

elements.callbackInput.addEventListener("change", () => {
  elements.callbackOptions.hidden = !elements.callbackInput.checked;
});

document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => document.getElementById(button.dataset.close).close()));
document.querySelectorAll(".task-filters button").forEach((button) => button.addEventListener("click", () => {
  document.querySelector(".task-filters button.active").classList.remove("active");
  button.classList.add("active");
  state.status = button.dataset.status;
  renderTasks();
}));

elements.searchInput.addEventListener("input", () => {
  state.query = elements.searchInput.value.trim().toLowerCase();
  if (state.data) render();
});
elements.refreshButton.addEventListener("click", refresh);
const autoRefresh = createAutoRefresh({
  refresh,
  interval: elements.interval,
  pauseButton: elements.pauseButton,
  refreshState: elements.refreshState,
  onResume: refresh,
});

refresh();
