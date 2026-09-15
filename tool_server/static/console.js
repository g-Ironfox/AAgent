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
  "modeInput", "timeoutInput", "callbackInput", "invokeError", "taskDialog", "detailTitle", "taskDetailBody",
  "cancelTaskButton",
].map((id) => [id, document.getElementById(id)]));

const statusNames = {
  pending: "等待中",
  working: "执行中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
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
  elements.failedCount.textContent = summary.statuses.failed + summary.statuses.cancelled;
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
    const statusMatch = state.status === "all" || task.status === state.status || (state.status === "failed" && task.status === "cancelled");
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
  elements.invokeError.hidden = true;
  elements.invokeDialog.showModal();
}

function renderTaskDetail(task) {
  elements.detailTitle.textContent = task.tool;
  elements.cancelTaskButton.hidden = !["pending", "working"].includes(task.status);
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
    const callback = elements.callbackInput.checked ? { type: "redis", queue: "main_agent_queue", event_type: "async_result" } : null;
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

elements.cancelTaskButton.addEventListener("click", async () => {
  if (!state.selectedTaskId) return;
  try {
    const task = await request(`/api/tasks/${state.selectedTaskId}/cancel`, { method: "POST" });
    renderTaskDetail(task);
    await refresh();
  } catch (error) {
    showNotice(`取消任务失败：${error.message}`);
  }
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
