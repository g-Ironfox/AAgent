export function createAutoRefresh({ refresh, interval, pauseButton, refreshState, onResume }) {
  let paused = false;
  let timer = null;

  function schedule() {
    window.clearTimeout(timer);
    if (!paused) timer = window.setTimeout(refresh, Number(interval.value));
  }

  interval.addEventListener('change', schedule);
  pauseButton.addEventListener('click', () => {
    paused = !paused;
    pauseButton.classList.toggle('active', paused);
    pauseButton.querySelector('.pause-icon').classList.toggle('play', paused);
    pauseButton.title = paused ? '继续自动刷新' : '暂停自动刷新';
    pauseButton.setAttribute('aria-label', pauseButton.title);
    refreshState.textContent = paused ? '自动刷新已暂停' : '自动刷新已开启';
    if (paused) schedule();
    else if (onResume) onResume();
    else schedule();
  });

  return { schedule };
}