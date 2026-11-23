export const finalStatuses = new Set(['completed', 'failed', 'terminated', 'killed', 'lost']);
export const statusLabels = {
  ready: '就绪', running: '运行中', blocked: '已挂起', waiting_for_input: '等待输入',
  completed: '已完成', failed: '失败', terminated: '已终止', killed: '已强制终止', lost: '运行状态丢失', unknown: '时间状态未知',
};
const eventStatuses = { created: 'ready', started: 'running', resumed: 'running',
  yielded: 'ready', blocked: 'blocked', woken: 'ready', completed: 'completed',
  failed: 'failed', terminated: 'terminated', killed: 'killed', lost: 'lost' };
export function timestamp(value) {
  if (value == null || value === '') return null;
  const time = new Date(value).getTime();
  return Number.isFinite(time) ? time : null;
}
export function formatDuration(value) {
  if (!Number.isFinite(value) || value < 0) return '—';
  if (value < 1000) return Math.round(value) + ' ms';
  if (value < 60000) return (value / 1000).toFixed(1) + ' 秒';
  if (value < 3600000) return (value / 60000).toFixed(1) + ' 分钟';
  return (value / 3600000).toFixed(1) + ' 小时';
}
export function waitLabel(wait) {
  if (!wait) return '—';
  const label = { terminal_message: '终端消息', process_exit: '子进程退出' }[wait.kind] || wait.kind || '事件';
  return label + (wait.process_id ? ' · ' + wait.process_id : '');
}
export function matches(process, { type = 'all', status = 'all', search = '' } = {}) {
  return (type === 'all' || (process.process_type || 'workflow') === type)
    && (status === 'all' || process.status === status)
    && (!search || [process.process_id, process.workflow_name, process.parent_process_id,
      process.root_process_id, process.terminal_id, process.wait_for?.process_id]
      .some(value => String(value || '').toLowerCase().includes(search.toLowerCase())));
}
// Events describe committed scheduling states; no node elapsed time is mistaken for CPU time.
export function buildSegments(process, start, end) {
  if (!(Number.isFinite(start) && Number.isFinite(end) && end > start)) return [];
  const events = (process.events || []).map((event, index) => ({
    time: timestamp(event.timestamp), status: event.status || eventStatuses[event.event] || 'unknown',
    wait: event.wait_for, index,
  })).filter(event => event.time !== null).sort((a, b) => a.time - b.time || a.index - b.index);
  const created = timestamp(process.start_time);
  if (created !== null && (!events.length || events[0].time > created)) {
    events.unshift({ time: created, status: process.process_type === 'terminal' ? 'waiting_for_input' : 'unknown' });
  }
  const finished = timestamp(process.finished_at);
  if (finished !== null && finalStatuses.has(process.status)
      && !events.some(event => event.time === finished && finalStatuses.has(event.status))) {
    events.push({ time: finished, status: process.status });
    events.sort((a, b) => a.time - b.time);
  }
  // Legacy snapshots without a final transition cannot prove how long a state lasted.
  // Also stop a failed/cancelled process at its last known transition.
  const terminalEvent = events.find(event => finalStatuses.has(event.status));
  const stop = Math.min(end, finished ?? terminalEvent?.time ?? end);
  const segments = [];
  for (let index = 0; index < events.length; index++) {
    const event = events[index];
    if (event.time > stop) break;
    const left = Math.max(start, event.time);
    if (finalStatuses.has(event.status)) {
      if (event.time >= start && event.time <= end) segments.push({ start: event.time, end: event.time, status: event.status, point: true });
      break;
    }
    const right = Math.min(stop, events[index + 1]?.time ?? stop);
    if (right > left) segments.push({ start: left, end: right, status: event.status, wait: event.wait });
  }
  return segments;
}
export function isPrecise(process) {
  const starts = (process.events || []).filter(event => event.event === 'started' || event.event === 'resumed');
  return starts.length > 0 && starts.every(event => event.dispatch === true);
}
