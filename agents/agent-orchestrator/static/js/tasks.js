/* tasks.js — Tasks modal: list tasks from tasks.json, trigger runs, show results */
(function () {
  'use strict';

  const POLL_MS = 3000;
  let _timer    = null;

  // ── Status badge ─────────────────────────────────────────────────────────────

  const STATUS_COLOR = {
    idle:      'var(--text3)',
    running:   '#4fc3f7',
    completed: '#81c784',
    failed:    '#e57373',
  };

  function _badge(status) {
    const color = STATUS_COLOR[status] || 'var(--text3)';
    return `<span style="color:${color};font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em">${status}</span>`;
  }

  function _scheduleLabel(sched) {
    if (!sched || sched === 'manual')        return 'manual';
    if (sched === 'on_start')               return 'on start';
    if (sched.startsWith('interval:')) {
      const secs = parseInt(sched.split(':')[1], 10);
      if (secs >= 3600) return `every ${secs / 3600}h`;
      if (secs >= 60)   return `every ${secs / 60}m`;
      return `every ${secs}s`;
    }
    return sched;
  }

  // ── Render ────────────────────────────────────────────────────────────────────

  function _render(tasks) {
    const el = document.getElementById('task-list');
    if (!el) return;

    if (!tasks || tasks.length === 0) {
      el.innerHTML = '<div style="color:var(--text3);font-size:13px;padding:8px 0">No tasks defined. Add tasks to tasks.json.</div>';
      return;
    }

    el.innerHTML = tasks.map(t => {
      const running = t.status === 'running';
      const resultHtml = t.last_result
        ? `<div class="task-result">${_esc(t.last_result.slice(0, 400))}${t.last_result.length > 400 ? '…' : ''}</div>`
        : (t.last_error
          ? `<div class="task-result" style="color:#e57373">${_esc(t.last_error)}</div>`
          : '');

      return `
        <div class="task-card">
          <div class="task-card-top">
            <div class="task-card-left">
              <div class="task-name">${_esc(t.name)}</div>
              <div class="task-meta">
                <span class="task-agent">${_esc(t.agent_id)}</span>
                <span class="task-sep">·</span>
                <span class="task-sched">${_scheduleLabel(t.schedule)}</span>
                ${t.last_run ? `<span class="task-sep">·</span><span class="task-time">last run ${_timeAgo(t.last_run)}</span>` : ''}
              </div>
              <div class="task-desc">${_esc(t.description)}</div>
            </div>
            <div class="task-card-right">
              ${_badge(t.status)}
              <button
                class="btn-run ${running ? 'running' : ''}"
                onclick="window._tasks.run('${t.id}')"
                ${running ? 'disabled' : ''}>
                ${running ? '…' : '▶ Run'}
              </button>
            </div>
          </div>
          ${resultHtml}
        </div>`;
    }).join('');
  }

  function _esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function _timeAgo(iso) {
    const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (diff < 60)    return `${diff}s ago`;
    if (diff < 3600)  return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return new Date(iso).toLocaleDateString();
  }

  // ── API calls ─────────────────────────────────────────────────────────────────

  async function _fetchTasks() {
    try {
      const r = await fetch('/api/tasks');
      if (!r.ok) return;
      const data = await r.json();
      _render(data.tasks || []);
    } catch (_) { /* network error — keep last render */ }
  }

  // ── Public API ────────────────────────────────────────────────────────────────

  window._tasks = {
    open() {
      document.getElementById('tasks-modal').classList.remove('hidden');
      _fetchTasks();
      _timer = setInterval(_fetchTasks, POLL_MS);
    },

    close() {
      document.getElementById('tasks-modal').classList.add('hidden');
      if (_timer) { clearInterval(_timer); _timer = null; }
    },

    async run(taskId) {
      try {
        await fetch(`/api/tasks/${taskId}/run`, { method: 'POST' });
        await _fetchTasks();
      } catch (_) {}
    },
  };

  // Close on overlay click
  document.getElementById('tasks-modal')
    .addEventListener('click', e => {
      if (e.target.id === 'tasks-modal') window._tasks.close();
    });

})();
