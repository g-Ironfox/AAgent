'use strict';
const $ = id => document.getElementById(id);
const state = {jobs: new Map(), job: null, jobId: null, epoch: 0, episode: null,
  episodeAfter: -1, episodePages: [], nextEpisodes: null, episodes: [], cursor: 0,
  moreEvents: false, jobsCursor: null, loadedMore: false, busy: false, optionsAt: 0};
const names = {queued: '排队中', running: '运行中', completed: '已完成', failed: '失败',
  success: '成功', max_steps: '达到步数上限', error: '错误', interrupted: '已中断', environment_done: '环境结束'};
function el(tag, cls, text) {const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n;}
function badge(status) {return el('span', 'badge ' + status, names[status] || status);}
function date(value) {return value ? new Date(value).toLocaleString('zh-CN', {hour12: false}) : '—';}
function duration(seconds) {if (seconds == null) return '—'; return seconds < 60 ? seconds.toFixed(1) + 's' : Math.floor(seconds / 60) + 'm ' + Math.floor(seconds % 60) + 's';}
function notice(message, success = false) {$('notice').hidden = !message; $('notice').className = success ? 'success' : ''; $('notice').textContent = message;}
async function api(url, options) {
  const response = await fetch(url, options);
  let data; try {data = await response.json();} catch {throw new Error('服务返回了无效响应');}
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
  return data;
}
async function options() {
  const data = await api('/api/options');
  const select = $('workflow'); const previous = select.value;
  select.replaceChildren(el('option', '', data.workflows.length ? '请选择 Workflow' : '暂无 Workflow，请先在 Agent WebUI 导入'));
  select.firstChild.value = '';
  for (const workflow of data.workflows) {const item = el('option', '', workflow.workflow_name || workflow.name); item.value = workflow.file_id; select.append(item);}
  select.value = previous;
  const online = data.workers.filter(item => item.online);
  const ready = online.filter(item => item.dataset_ready);
  const instances = new Set(online.map(item => item.instance_id || item.worker_id));
  const busy = online.filter(item => item.job_id).length;
  $('worker-status').textContent = online.length ? instances.size + ' 个 worker · ' + busy + ' / ' + online.length + ' 进程运行 · ' + ready.length + ' 进程数据就绪' : '暂无在线 worker · 任务将排队';
  $('worker-status').className = 'connection' + (ready.length ? ' online' : '');
  state.optionsAt = Date.now();
}
function renderJobs() {
  const container = $('jobs'); container.replaceChildren();
  if (!state.jobs.size) container.append(el('p', 'empty', '暂无测试任务，在左侧发布第一次评测。'));
  for (const job of [...state.jobs.values()].sort((a, b) => b.created_at.localeCompare(a.created_at) || b.job_id.localeCompare(a.job_id))) {
    const button = el('button', 'job' + (job.job_id === state.jobId ? ' selected' : ''));
    const left = el('div'); left.append(el('div', 'job-name', job.config.name), el('div', 'job-meta', job.workflow_name + ' · ' + job.config.split + ' · ' + date(job.created_at)));
    const right = el('div', 'job-end'); right.append(badge(job.status), el('div', 'job-meta', job.summary.completed + ' / ' + job.summary.requested + ' episodes'));
    button.append(left, right); button.onclick = () => selectJob(job.job_id); container.append(button);
  }
  $('more-jobs').hidden = !state.jobsCursor;
}
async function loadJobs(more = false) {
  const params = new URLSearchParams();
  if (more && state.jobsCursor) params.set('before', state.jobsCursor);
  if ($('status-filter').value) params.set('status', $('status-filter').value);
  const data = await api('/api/jobs?' + params);
  if (!more && !state.loadedMore) state.jobs.clear();
  for (const job of data.items) state.jobs.set(job.job_id, job);
  if (more) state.loadedMore = true;
  if (more || !state.loadedMore) state.jobsCursor = data.next_cursor;
  renderJobs();
}
async function selectJob(id) {
  state.jobId = id; state.job = null; state.episode = null; state.cursor = 0;
  state.episodeAfter = -1; state.episodePages = []; state.epoch++;
  location.hash = id;
  $('detail').replaceChildren($('detail-template').content.cloneNode(true));
  $('reuse').onclick = reuse;
  $('next-episodes').onclick = () => episodePage(true);
  $('prev-episodes').onclick = () => episodePage(false);
  $('more-events').onclick = () => loadEvents().catch(error => notice(error.message));
  renderJobs();
  try {await refreshDetail();} catch (error) {notice(error.message);}
}
function renderDetail(job) {
  state.job = job;
  $('detail-name').textContent = job.config.name;
  $('detail-meta').textContent = job.job_id + ' · ' + job.workflow_name + ' · ' + job.config.split + ' · seed ' + job.config.seed;
  $('job-error').hidden = !job.error; $('job-error').textContent = job.error || '';
  $('dispatch-error').hidden = !job.dispatch_error; $('dispatch-error').textContent = '任务已保存，等待队列连接恢复后自动投递：' + (job.dispatch_error || '');
  const s = job.summary;
  $('metric-progress').textContent = s.completed + ' / ' + s.requested;
  $('metric-rate').textContent = s.completed ? (s.success_rate * 100).toFixed(1) + '%' : '—';
  $('metric-results').textContent = s.successes + ' / ' + s.errors;
  const elapsed = job.started_at ? (new Date(job.finished_at || Date.now()) - new Date(job.started_at)) / 1000 : null;
  $('metric-duration').textContent = duration(elapsed);
  $('progress-bar').style.width = (s.completed / s.requested * 100) + '%';
  $('progress-text').textContent = (names[job.status] || job.status) + ' · ' + date(job.created_at) + (job.status === 'running' && job.current_episode != null ? ' · 当前 Episode ' + (job.current_episode + 1) : '');
  $('live').textContent = ['queued', 'running'].includes(job.status) ? '实时更新' : '已归档';
}
function selectEpisode(index) {
  state.episode = index; state.cursor = 0; state.moreEvents = false; state.epoch++;
  $('trace').replaceChildren(); $('trace-trimmed').hidden = true;
  renderEpisodes(); loadEvents().catch(error => notice(error.message));
}
function renderEpisodes() {
  const body = $('episodes'); body.replaceChildren();
  const chart = $('chart'); chart.replaceChildren();
  const maximum = Math.max(1, ...state.episodes.map(item => item.steps || 0));
  for (const item of state.episodes) {
    const row = el('tr', item.index === state.episode ? 'selected' : ''); row.dataset.index = item.index;
    row.append(el('td', 'mono', '#' + (item.index + 1)));
    const status = el('td'); status.append(badge(item.status)); row.append(status,
      el('td', 'mono', item.steps), el('td', 'mono', item.score == null ? '—' : item.score), el('td', 'mono', duration(item.duration_seconds)));
    row.onclick = () => selectEpisode(item.index); body.append(row);
    const bar = el('button', 'bar ' + item.status + (item.index === state.episode ? ' selected' : ''));
    bar.style.height = Math.max(4, (item.steps || 0) / maximum * 65) + 'px';
    bar.title = 'Episode ' + (item.index + 1) + ' · ' + (item.steps || 0) + ' steps · ' + (names[item.status] || item.status);
    bar.setAttribute('aria-label', bar.title); bar.append(el('span', '', item.index + 1)); bar.onclick = row.onclick; chart.append(bar);
  }
  if (!state.episodes.length) {body.append(el('tr', 'empty', '等待 worker 开始测试…')); chart.append(el('p', 'hint', '运行后显示每个 episode 的步数'));}
  $('prev-episodes').disabled = !state.episodePages.length;
  $('next-episodes').disabled = state.nextEpisodes == null;
  $('episode-page').textContent = '第 ' + (state.episodePages.length + 1) + ' 页';
  const episode = state.episodes.find(item => item.index === state.episode);
  $('trace-episode').textContent = episode ? '#' + (episode.index + 1) : '等待开始';
  $('terminal-id').textContent = episode ? 'Terminal · ' + episode.terminal_id : '';
}
async function episodePage(next) {
  if (next) {state.episodePages.push(state.episodeAfter); state.episodeAfter = state.nextEpisodes;}
  else state.episodeAfter = state.episodePages.pop() ?? -1;
  state.episode = null; state.cursor = 0; state.epoch++;
  $('trace').replaceChildren();
  try {await refreshDetail();} catch (error) {notice(error.message);}
}
async function refreshDetail() {
  if (!state.jobId) return;
  const id = state.jobId, epoch = state.epoch;
  const [job, page] = await Promise.all([api('/api/jobs/' + id), api('/api/jobs/' + id + '/episodes?limit=50&after=' + state.episodeAfter)]);
  if (id !== state.jobId || epoch !== state.epoch) return;
  renderDetail(job);
  if (state.jobs.has(id)) {state.jobs.set(id, job); renderJobs();}
  state.episodes = page.items; state.nextEpisodes = page.next_cursor;
  if (state.episode == null && page.items.length) state.episode = page.items[0].index;
  renderEpisodes(); await loadEvents();
}
let loadingEvents = false;
async function loadEvents() {
  if (state.episode == null || loadingEvents) return;
  loadingEvents = true;
  const epoch = state.epoch, id = state.jobId, episode = state.episode;
  try {
    const page = await api('/api/jobs/' + id + '/events?episode=' + episode + '&after=' + state.cursor);
    if (epoch !== state.epoch) return;
    state.cursor = page.next_cursor; state.moreEvents = page.has_more;
    const trace = $('trace'); const bottom = trace.scrollHeight - trace.scrollTop - trace.clientHeight < 70;
    for (const record of page.items) {
      const entry = el('div', 'trace-entry ' + record.direction);
      const step = record.direction === 'action' ? record.step : record.message?.step;
      const label = el('div', 'trace-label', record.direction.toUpperCase() + (step == null ? '' : ' · STEP ' + step));
      label.append(el('span', '', new Date(record.created_at).toLocaleTimeString('zh-CN', {hour12: false})));
      entry.append(label, el('pre', '', record.direction === 'action' ? record.text : record.direction === 'observation' ? record.message.text : JSON.stringify(record.result, null, 2)));
      if (record.direction === 'observation' && record.message.done) entry.append(el('p', 'hint', '结束原因 · ' + record.message.reason));
      if (record.message?.admissible_commands) {const detail = el('details'); detail.append(el('summary', 'hint', '合法动作列表'), el('pre', '', record.message.admissible_commands.join('\n'))); entry.append(detail);}
      trace.append(entry);
    }
    while (trace.children.length > 1000) {trace.firstChild.remove(); $('trace-trimmed').hidden = false;}
    if (bottom) trace.scrollTop = trace.scrollHeight;
    $('more-events').hidden = !page.has_more;
  } finally {loadingEvents = false;}
}
function reuse() {
  if (!state.job) return;
  const form = $('job-form'), config = state.job.config;
  for (const [key, value] of Object.entries(config)) {
    const field = form.elements.namedItem(key); if (!field) continue;
    if (key === 'inputs') field.value = JSON.stringify(value, null, 2);
    else if (field.type === 'checkbox') field.checked = value;
    else field.value = value;
  }
  form.elements.name.value = config.name + ' · rerun';
  form.scrollIntoView({behavior: 'smooth', block: 'start'});
  notice('已填入配置，点击“发布测试”开始新的评测。', true);
}
$('job-form').onsubmit = async event => {
  event.preventDefault(); const form = event.currentTarget, values = new FormData(form);
  const config = Object.fromEntries(values);
  try {
    config.inputs = JSON.parse(config.inputs);
    if (!config.inputs || Array.isArray(config.inputs) || typeof config.inputs !== 'object') throw new Error('Workflow inputs 必须是 JSON 对象');
    for (const key of ['episodes', 'max_steps', 'seed', 'action_timeout', 'startup_timeout']) config[key] = Number(config[key]);
    config.admissible_commands = form.elements.admissible_commands.checked;
    $('submit').disabled = true;
    const job = await api('/api/jobs', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(config)});
    $('status-filter').value = ''; state.jobs.clear(); state.loadedMore = false; await loadJobs(); await selectJob(job.job_id);
    notice('测试已发布，worker 将自动领取。', true);
  } catch (error) {notice(error.message);} finally {$('submit').disabled = false;}
};
async function refresh() {
  if (state.busy) return; state.busy = true;
  try {
    await loadJobs(); await refreshDetail();
    if (Date.now() - state.optionsAt > 15000) await options();
  } catch (error) {notice(error.message);} finally {state.busy = false;}
}
$('refresh').onclick = refresh;
$('status-filter').onchange = () => {state.jobs.clear(); state.loadedMore = false; loadJobs().catch(error => notice(error.message));};
$('more-jobs').onclick = () => loadJobs(true).catch(error => notice(error.message));
async function init() {
  try {await options(); await loadJobs(); const id = location.hash.slice(1); if (/^[a-f0-9]{32}$/.test(id)) await selectJob(id);}
  catch (error) {notice(error.message);}
  setInterval(refresh, 2500);
}
init();
