window._urls = (() => {
  const modal   = () => document.getElementById('urls-modal');
  const list    = () => document.getElementById('urls-list');
  const note    = () => document.getElementById('urls-note');

  async function refresh() {
    list().innerHTML = '<div style="color:var(--text3);font-size:13px">Checking…</div>';
    try {
      const res  = await fetch('/api/services');
      const data = await res.json();
      render(data.services || []);
      const t = new Date().toLocaleTimeString();
      note().textContent = `Last checked ${t}`;
    } catch (e) {
      list().innerHTML = `<div style="color:var(--danger);font-size:13px">Failed to load: ${e}</div>`;
    }
  }

  function render(services) {
    if (!services.length) {
      list().innerHTML = '<div style="color:var(--text3);font-size:13px">No services declared. Add a <code>services</code> field in agents.conf.</div>';
      return;
    }

    // Group by agent
    const byAgent = {};
    services.forEach(s => {
      const key = s.agent_name;
      if (!byAgent[key]) byAgent[key] = [];
      byAgent[key].push(s);
    });

    let html = '';
    for (const [agentName, svcs] of Object.entries(byAgent)) {
      html += `<div class="url-group">
        <div class="url-group-title">${agentName}</div>`;
      svcs.forEach(s => {
        const dot   = s.reachable ? 'url-dot up' : 'url-dot down';
        const label = s.reachable ? 'up' : 'down';
        html += `
        <div class="url-row">
          <span class="${dot}" title="${label}"></span>
          <div class="url-info">
            <span class="url-name">${s.name}</span>
            <a class="url-link" href="${s.url}" target="_blank">${s.url}</a>
          </div>
          <button class="url-copy" onclick="_urls._copy(this,'${s.url}')" title="Copy URL">⎘</button>
          <a class="url-open" href="${s.url}" target="_blank" title="Open in new tab">↗</a>
        </div>`;
      });
      html += `</div>`;
    }
    list().innerHTML = html;
  }

  function open() {
    modal().classList.remove('hidden');
    refresh();
  }

  function close() {
    modal().classList.add('hidden');
  }

  function _copy(btn, url) {
    navigator.clipboard.writeText(url).then(() => {
      const orig = btn.textContent;
      btn.textContent = '✓';
      btn.style.color = 'var(--success, #4caf50)';
      setTimeout(() => { btn.textContent = orig; btn.style.color = ''; }, 1500);
    });
  }

  return { open, close, refresh, _copy };
})();
