/**
 * Dashboard — main orchestrator.
 * Wires up EventStream, AlertSystem, agent grid, detail panel, chat, logs, memory.
 *
 * Views:
 *   grid   — monitoring cards for all agents (default)
 *   detail — selected agent: Chat | Logs | Memory
 */

/* ── Utility ── */
window.esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const $  = id => document.getElementById(id);
const scrollBot = el => { el.scrollTop = el.scrollHeight; };

class Dashboard {
  constructor() {
    this.sound  = new SoundSystem();
    this.alerts = new AlertSystem(this.sound);
    this.stream = new EventStream();

    this._agents       = [];       // latest snapshot from API
    this._selected     = null;     // selected agent id
    this._parentAgent  = null;     // parent agent id when viewing a sub-agent
    this._view         = 'grid';   // 'grid' | 'detail'
    this._currentTab   = 'chat';
    this._ws           = null;
    this._logEs        = null;
    this._changeCount  = 0;
    this._changeOpen   = true;
    this._currentMsgEl = null;
  }

  // ── Boot ──────────────────────────────────────────────────────────────────

  async init() {
    window._dash = this;
    this._loadTheme();
    await this.alerts.loadSettings();
    this._bindStream();
    this.stream.connect();
    await this._fetchAgents();
    this._renderGrid();
    this._bindUI();
  }

  // ── Theme ─────────────────────────────────────────────────────────────────

  _loadTheme() {
    const saved = localStorage.getItem('dash-theme') || 'dark';
    this._applyTheme(saved);
  }

  setTheme(theme) {
    localStorage.setItem('dash-theme', theme);
    this._applyTheme(theme);
  }

  _applyTheme(theme) {
    document.body.dataset.theme = theme;
    document.getElementById('theme-dark')?.classList.toggle('active', theme === 'dark');
    document.getElementById('theme-light')?.classList.toggle('active', theme === 'light');
  }

  // ── Event stream bindings ─────────────────────────────────────────────────

  _bindStream() {
    const s = this.stream;

    s.on('_connected',    () => this._setMonitorBadge(true));
    s.on('_disconnected', () => this._setMonitorBadge(false));

    s.on('init', data => {
      this._agents = data.agents || [];
      this._renderGrid();
      this._updateSidebar();
      this._updateHeaderStats();
    });

    s.on('status_change', data => {
      this._agents = this._agents.map(a =>
        a.id === data.agent_id ? { ...a, status: data.status } : a
      );
      this._renderGrid();
      this._updateSidebar();
      this._updateHeaderStats();
      if (this._selected === data.agent_id) this._updateDetailHeader();
    });

    s.on('alert', data => {
      this.alerts.handle(data);
    });

    s.on('workspace_change', data => {
      this._addChange(data);
    });
  }

  _setMonitorBadge(on) {
    const el = $('monitor-badge');
    el.textContent = on ? '● MONITOR ON' : '● MONITOR OFF';
    el.className   = 'monitor-badge' + (on ? '' : ' off');
  }

  // ── Agent fetch ───────────────────────────────────────────────────────────

  async _fetchAgents() {
    try {
      const res = await fetch('/api/agents');
      const d   = await res.json();
      this._agents = d.agents || [];
    } catch {}
  }

  // ── Header stats ──────────────────────────────────────────────────────────

  _updateHeaderStats() {
    const visible = this._agents.filter(a => !a.hidden);
    const running = visible.filter(a => a.status === 'running').length;
    $('stat-running').textContent = `${running}/${visible.length} running`;
  }

  // ── Grid view ─────────────────────────────────────────────────────────────

  _renderGrid() {
    const grid = $('grid-view');
    if (!grid) return;
    grid.innerHTML = '';
    for (const a of this._agents.filter(a => !a.hidden)) {
      const card = document.createElement('div');
      card.className = 'agent-card ' + a.status + (this._selected === a.id ? ' selected' : '');
      card.dataset.id = a.id;
      const statusLabel = { running: 'Running', stopped: 'Stopped', unavailable: 'Unavailable', unknown: 'Unknown' };
      const uptimeRow = a.status === 'running'
        ? `<div class="stat-box"><div class="stat-label">Uptime</div><div class="stat-value green">${esc(a.uptime)}</div></div>`
        : `<div class="stat-box"><div class="stat-label">Down since</div><div class="stat-value text2">${esc(a.downtime)}</div></div>`;
      card.innerHTML = `
        <div class="card-hdr">
          <div class="card-name">${esc(a.name)}</div>
          <span class="status-badge ${a.status}">${statusLabel[a.status] || a.status}</span>
          <span class="card-type">${a.type}</span>
        </div>
        <div class="card-desc">${esc(a.description)}</div>
        <div class="card-stats">
          ${uptimeRow}
          <div class="stat-box">
            <div class="stat-label">Last check</div>
            <div class="stat-value text3">${esc(a.last_check)}</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Memory</div>
            <div class="stat-value text3">${a.mem_files.length} file${a.mem_files.length !== 1 ? 's' : ''}</div>
          </div>
        </div>
        <div class="card-footer">
          <div class="dot ${a.status}"></div>
          <button class="card-open-btn">Open →</button>
        </div>`;
      card.querySelector('.card-open-btn').onclick = (e) => { e.stopPropagation(); this.openDetail(a.id); };
      card.onclick = () => this.openDetail(a.id);
      grid.appendChild(card);
    }
  }

  // ── Sidebar agent list ────────────────────────────────────────────────────

  _updateSidebar() {
    const list = $('sidebar-agents');
    if (!list) return;
    list.innerHTML = this._agents.filter(a => !a.hidden).map(a => `
      <div class="agent-item${this._selected === a.id ? ' active' : ''}" onclick="window._dash.openDetail('${a.id}')">
        <div class="agent-item-name">${esc(a.name)}</div>
        <div class="agent-item-meta">
          <div class="dot ${a.status}"></div>
          <span class="status-txt ${a.status}">${a.status}</span>
          <span class="type-tag">${a.type}</span>
        </div>
      </div>`).join('');
  }

  // ── View switching ────────────────────────────────────────────────────────

  // ── Services view ────────────────────────────────────────────────────────

  showServices() {
    this._view = 'services';
    $('grid-view').classList.add('hidden');
    $('detail-view').classList.add('hidden');
    $('services-view').classList.remove('hidden');
    document.querySelectorAll('.vbtn').forEach(b => b.classList.toggle('active', b.dataset.view === 'services'));
    this._disconnectChat();
    this._disconnectLogs();
    this.refreshServices();
  }

  async refreshServices() {
    const list = $('svc-list');
    const note = $('svc-note');
    if (!list) return;
    try {
      const res  = await fetch('/api/services');
      const data = await res.json();
      const svcs = data.services || [];
      note.textContent = `Last checked ${new Date().toLocaleTimeString()} · ${svcs.filter(s => s.reachable).length}/${svcs.length} up`;
      if (!svcs.length) {
        list.innerHTML = '<div class="svc-empty">No services declared. Add a <code>services</code> field in agents.conf.</div>';
        return;
      }
      list.innerHTML = svcs.map(s => `
        <div class="svc-row ${s.reachable ? 'up' : 'down'}">
          <div class="svc-status-col">
            <span class="svc-dot ${s.reachable ? 'up' : 'down'}"></span>
            <span class="svc-status-txt">${s.reachable ? 'UP' : 'DOWN'}</span>
          </div>
          <div class="svc-info">
            <div class="svc-name">${esc(s.name)}</div>
            <div class="svc-agent">managed by ${esc(s.agent_name)}</div>
          </div>
          <a class="svc-url" href="${s.url}" target="_blank">${s.url}</a>
          <div class="svc-actions">
            <button class="svc-btn" onclick="_dash._copySvcUrl(this,'${s.url}')" title="Copy URL">⎘ Copy</button>
            <a class="svc-btn open" href="${s.url}" target="_blank" title="Open">↗ Open</a>
          </div>
        </div>`).join('');
    } catch (e) {
      list.innerHTML = `<div class="svc-empty" style="color:var(--danger)">Failed to load: ${e}</div>`;
    }
  }

  _copySvcUrl(btn, url) {
    navigator.clipboard.writeText(url).then(() => {
      const orig = btn.textContent;
      btn.textContent = '✓ Copied';
      btn.style.color = 'var(--green)';
      setTimeout(() => { btn.textContent = orig; btn.style.color = ''; }, 1500);
    });
  }

  showGrid() {
    if (this._parentAgent) {
      // navigating back from a sub-agent → go to parent's detail
      const parentId = this._parentAgent;
      this._parentAgent = null;
      this.openDetail(parentId);
      return;
    }
    this._view = 'grid';
    $('grid-view').classList.remove('hidden');
    $('detail-view').classList.add('hidden');
    $('services-view')?.classList.add('hidden');
    document.querySelectorAll('.vbtn').forEach(b => b.classList.toggle('active', b.dataset.view === 'grid'));
    this._selected = null;
    this._renderGrid();
    this._updateSidebar();
    this._disconnectChat();
    this._disconnectLogs();
  }

  openDetail(agentId) {
    this._selected = agentId;
    this._view = 'detail';
    $('grid-view').classList.add('hidden');
    $('detail-view').classList.remove('hidden');
    document.querySelectorAll('.vbtn').forEach(b => b.classList.toggle('active', b.dataset.view === 'detail'));
    this._renderGrid();       // update card selection highlight
    this._updateSidebar();

    const agent = this._agents.find(a => a.id === agentId);
    if (!agent) return;
    this._updateDetailHeader(agent);

    // Show/hide tabs based on agent capabilities
    const isHttp = agent.connector === 'http';
    const hasSubs = agent.sub_agents && agent.sub_agents.length > 0;

    const tabContainers = $('tab-containers');
    if (tabContainers) tabContainers.style.display = isHttp ? '' : 'none';

    const tabAgents = $('tab-agents');
    if (tabAgents) tabAgents.style.display = hasSubs ? '' : 'none';

    const tabDocs = $('tab-apidocs');
    if (tabDocs) tabDocs.style.display = isHttp ? '' : 'none';

    // Clear iframe when switching agents
    const frame = document.getElementById('apidocs-frame');
    if (frame) frame.src = '';
    this._currentDocsUrl = isHttp && agent.api_url
      ? agent.api_url.replace(/\/$/, '') + '/docs'
      : null;

    // Update back button — show breadcrumb when navigating from a parent agent
    const backBtn = document.querySelector('.btn-back');
    if (backBtn) {
      if (this._parentAgent) {
        const parent = this._agents.find(a => a.id === this._parentAgent);
        backBtn.textContent = `← ${parent ? parent.name : 'Back'}`;
      } else {
        backBtn.textContent = '← Grid';
      }
    }

    this.switchTab('chat');
    this._resetChat();
    this._connectChat(agentId);
    this._connectLogs(agentId);
    this._loadMemory(agentId);
  }

  _updateDetailHeader(agent) {
    if (!agent) agent = this._agents.find(a => a.id === this._selected);
    if (!agent) return;
    $('detail-dot').className   = `dot lg ${agent.status}`;
    $('detail-name').textContent = agent.name;
    $('detail-sub').textContent  = `${agent.status} · uptime: ${agent.uptime}`;
    $('btn-start').disabled = agent.status === 'running';
    $('btn-stop').disabled  = agent.status !== 'running';
  }

  switchTab(name) {
    this._currentTab = name;
    document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    document.querySelectorAll('.pane').forEach(p => p.classList.toggle('active', p.id === `pane-${name}`));
    if (name === 'containers' && this._selected) this._loadContainers(this._selected);
    if (name === 'agents'    && this._selected) this._loadSubAgents(this._selected);
    if (name === 'apidocs') {
      const frame = document.getElementById('apidocs-frame');
      if (frame && this._currentDocsUrl && !frame.src.endsWith('/docs')) {
        frame.src = this._currentDocsUrl;
      }
    }
  }

  // ── Agent actions ─────────────────────────────────────────────────────────

  async startAgent() {
    if (!this._selected) return;
    $('btn-start').disabled = true;
    try {
      const res = await fetch(`/api/agents/${this._selected}/start`, { method: 'POST' });
      const d   = await res.json();
      if (d.ok === false) {
        const msg = [d.detail, d.output].filter(Boolean).join('\n\n');
        this._showStartError(msg || d.error || 'Start failed');
        $('btn-start').disabled = false;
        return;
      }
    } catch (_) {}
    setTimeout(() => {
      this._fetchAgents().then(() => { this._renderGrid(); this._updateSidebar(); this._updateDetailHeader(); });
      if (this._selected) this._connectChat(this._selected);
    }, 4000);
  }

  _showStartError(msg) {
    const existing = $('start-error-banner');
    if (existing) existing.remove();
    const div = document.createElement('div');
    div.id        = 'start-error-banner';
    div.className = 'start-error-banner';
    div.textContent = msg;
    $('detail-hdr').insertAdjacentElement('afterend', div);
    setTimeout(() => div.remove(), 10000);
  }

  async stopAgent() {
    if (!this._selected) return;
    $('btn-stop').disabled = true;
    await fetch(`/api/agents/${this._selected}/stop`, { method: 'POST' }).catch(() => {});
    setTimeout(() => this._fetchAgents().then(() => { this._renderGrid(); this._updateSidebar(); this._updateDetailHeader(); }), 3000);
  }

  // ── Chat ──────────────────────────────────────────────────────────────────

  _connectChat(agentId) {
    this._disconnectChat();
    this._currentMsgEl = null;
    this._ws = new WebSocket(`ws://${location.host}/ws/agents/${agentId}/chat`);
    this._ws.onmessage = e => this._handleChatMsg(JSON.parse(e.data));
    this._ws.onclose   = () => this._enableInput();
    this._enableInput();
  }

  _disconnectChat() {
    if (this._ws) { this._ws.close(); this._ws = null; }
  }

  _resetChat() {
    $('chat-msgs').innerHTML = '';
    this._currentMsgEl = null;
    this._enableInput();
  }

  _handleChatMsg(msg) {
    const feed = $('chat-msgs');
    if (msg.type === 'history_msg') {
      const div = document.createElement('div');
      div.className = 'msg history';
      const roleLabel = msg.role === 'user' ? 'You' : 'Agent';
      const roleClass = msg.role === 'user' ? 'user' : 'agent';
      div.innerHTML = `<div class="msg-role ${roleClass}">${roleLabel}</div>`
        + `<div class="msg-body">${esc(msg.content)}</div>`
        + (msg.ts ? `<div class="msg-ts">${esc(msg.ts)}</div>` : '');
      feed.appendChild(div);
      scrollBot(feed);
      return;
    }
    if (msg.type === 'text') {
      feed.querySelector('.thinking-wrap')?.remove();
      if (!this._currentMsgEl) {
        const wrap = document.createElement('div');
        wrap.className = 'msg';
        wrap.innerHTML = '<div class="msg-role agent">Agent</div><div class="msg-body"></div>';
        feed.appendChild(wrap);
        this._currentMsgEl = wrap.querySelector('.msg-body');
      }
      this._currentMsgEl.textContent += msg.content;
      scrollBot(feed);
    }
    if (msg.type === 'tool_call') {
      feed.querySelector('.thinking-wrap')?.remove();
      const div = document.createElement('div');
      div.id = `tc-${msg.id}`;
      div.className = 'tool-block';
      div.innerHTML = `<span class="tool-n">[${esc(msg.name)}]</span><span class="tool-i">${esc(JSON.stringify(msg.input||{}).slice(0,120))}</span>`;
      feed.appendChild(div);
      scrollBot(feed);
    }
    if (msg.type === 'tool_result') {
      const el = $(`tc-${msg.id}`);
      if (el) {
        const r = document.createElement('div');
        r.className = 'tool-r';
        r.textContent = '→ ' + JSON.stringify(msg.result).slice(0, 300);
        el.appendChild(r);
        scrollBot(feed);
      }
    }
    if (msg.type === 'error') {
      feed.querySelector('.thinking-wrap')?.remove();
      const div = document.createElement('div');
      div.className = 'msg';
      div.innerHTML = `<div class="msg-role err">Error</div><div class="msg-body red">${esc(msg.content)}</div>`;
      feed.appendChild(div);
      scrollBot(feed);
    }
    if (msg.type === 'done') {
      this._currentMsgEl = null;
      this._enableInput();
      if (this._selected) this._loadMemory(this._selected);
    }
  }

  sendMsg() {
    const input = $('chat-in');
    const text  = input.value.trim();
    if (!text || !this._ws || this._ws.readyState !== WebSocket.OPEN) return;
    const feed = $('chat-msgs');

    const uDiv = document.createElement('div');
    uDiv.className = 'msg';
    uDiv.innerHTML = `<div class="msg-role user">You</div><div class="msg-body">${esc(text)}</div>`;
    feed.appendChild(uDiv);

    const tDiv = document.createElement('div');
    tDiv.className = 'msg thinking-wrap';
    tDiv.innerHTML = '<div class="msg-role agent">Agent</div><div class="thinking">thinking…</div>';
    feed.appendChild(tDiv);
    scrollBot(feed);

    this._ws.send(JSON.stringify({ content: text }));
    input.value = '';
    this._disableInput();
    this._currentMsgEl = null;
  }

  _enableInput()  { $('chat-in').disabled = false; $('btn-send').disabled = false; $('chat-in').focus(); }
  _disableInput() { $('chat-in').disabled = true;  $('btn-send').disabled = true; }

  // ── Logs ──────────────────────────────────────────────────────────────────

  _connectLogs(agentId) {
    this._disconnectLogs();
    $('log-stream').innerHTML = '';
    this._logEs = new EventSource(`/api/agents/${agentId}/logs/stream`);
    this._logEs.onmessage = e => {
      const d = JSON.parse(e.data);
      if (!d.line) return;
      const div = document.createElement('div');
      div.className = 'log-line';
      div.textContent = d.line;
      $('log-stream').appendChild(div);
      scrollBot($('log-stream'));
    };
  }

  _disconnectLogs() {
    if (this._logEs) { this._logEs.close(); this._logEs = null; }
  }

  // ── Memory ────────────────────────────────────────────────────────────────

  async _loadMemory(agentId) {
    const res  = await fetch(`/api/agents/${agentId}/memory`).catch(() => null);
    if (!res) return;
    const data = await res.json();
    const list = $('mem-list');
    list.innerHTML = '';
    for (const f of (data.files || [])) {
      const div = document.createElement('div');
      div.className = 'mem-item';
      div.textContent = f;
      div.onclick = () => this._openMemFile(agentId, f, div);
      list.appendChild(div);
    }
  }

  async _openMemFile(agentId, filename, el) {
    document.querySelectorAll('.mem-item').forEach(e => e.classList.remove('active'));
    el.classList.add('active');
    const res  = await fetch(`/api/agents/${agentId}/memory/${encodeURIComponent(filename)}`).catch(() => null);
    if (!res) return;
    const data = await res.json();
    $('mem-body').textContent = data.content || data.error || '(empty)';
  }

  // ── Workspace changes ─────────────────────────────────────────────────────

  _addChange(ev) {
    this._changeCount++;
    $('ch-count').textContent = this._changeCount;
    const feed = $('change-feed');
    const div  = document.createElement('div');
    div.className = 'ch-ev';
    let html = `<div class="ch-ts">${esc(ev.ts)}</div>`;
    for (const l of (ev.added   || [])) html += `<div class="ch-line ch-add">+ ${esc(l)}</div>`;
    for (const l of (ev.removed || [])) html += `<div class="ch-line ch-rem">- ${esc(l)}</div>`;
    div.innerHTML = html;
    feed.insertBefore(div, feed.firstChild);
  }

  toggleChanges() {
    this._changeOpen = !this._changeOpen;
    $('change-feed').classList.toggle('hidden', !this._changeOpen);
    $('ch-toggle').textContent = this._changeOpen ? '▴' : '▾';
  }

  // ── Settings modal ────────────────────────────────────────────────────────

  openSettings() {
    const s = this.alerts.getSettings();
    $('s-enabled').checked     = s.enabled;
    $('s-volume').value        = Math.round((s.volume || 0.7) * 100);
    $('s-vol-val').textContent = $('s-volume').value + '%';

    for (const [ruleId, rule] of Object.entries(s.rules || {})) {
      const en  = $(`s-${ruleId}-en`);
      const snd = $(`s-${ruleId}-snd`);
      const dur = $(`s-${ruleId}-dur`);
      if (en)  en.checked  = rule.enabled;
      if (snd) snd.value   = rule.sound;
      if (dur) dur.value   = rule.duration;
    }
    $('settings-modal').classList.remove('hidden');
  }

  closeSettings() {
    $('settings-modal').classList.add('hidden');
  }

  async saveSettings() {
    const s = this.alerts.getSettings();
    s.enabled = $('s-enabled').checked;
    s.volume  = parseInt($('s-volume').value) / 100;
    for (const ruleId of Object.keys(s.rules || {})) {
      const en  = $(`s-${ruleId}-en`);
      const snd = $(`s-${ruleId}-snd`);
      const dur = $(`s-${ruleId}-dur`);
      if (en)  s.rules[ruleId].enabled  = en.checked;
      if (snd) s.rules[ruleId].sound    = snd.value;
      if (dur) s.rules[ruleId].duration = parseInt(dur.value);
    }
    await this.alerts.saveSettings(s);
    this.closeSettings();
  }

  async testAlert(type) {
    await fetch(`/api/alerts/test/${type}`, { method: 'POST' });
  }

  // ── Containers ────────────────────────────────────────────────────────────

  // ── Sub-agents tab ────────────────────────────────────────────────────────

  async _loadSubAgents(agentId) {
    const grid = $('sub-agents-grid');
    if (!grid) return;
    grid.innerHTML = '<div style="padding:16px;color:var(--text3);font-size:13px">Loading…</div>';
    try {
      const res  = await fetch(`/api/agents/${agentId}/sub-agents`);
      const data = await res.json();
      const subs = data.sub_agents || [];
      if (!subs.length) {
        grid.innerHTML = '<div style="padding:16px;color:var(--text3);font-size:13px">No sub-agents configured.</div>';
        return;
      }
      grid.innerHTML = subs.map(a => {
        const statusLabel = { running: 'Running', stopped: 'Stopped', unknown: 'Unknown' };
        return `
        <div class="sub-agent-card ${a.status}" onclick="window._dash._openSubAgent('${agentId}','${a.id}')">
          <div class="sub-agent-hdr">
            <div class="dot ${a.status}"></div>
            <div class="sub-agent-name">${esc(a.name)}</div>
            <span class="status-badge ${a.status}">${statusLabel[a.status] || a.status}</span>
          </div>
          <div class="sub-agent-desc">${esc(a.description)}</div>
          <div class="sub-agent-meta">
            ${a.status === 'running'
              ? `<span class="sub-agent-stat green">↑ ${esc(a.uptime)}</span>`
              : `<span class="sub-agent-stat text3">↓ ${esc(a.downtime)}</span>`}
            <span class="sub-agent-stat text3">${a.mem_files.length} memory file${a.mem_files.length !== 1 ? 's' : ''}</span>
          </div>
          <div class="sub-agent-open">Open →</div>
        </div>`;
      }).join('');
    } catch (e) {
      grid.innerHTML = `<div style="padding:16px;color:var(--danger);font-size:13px">Failed: ${e}</div>`;
    }
  }

  _openSubAgent(parentId, subAgentId) {
    this._parentAgent = parentId;
    this.openDetail(subAgentId);
  }

  refreshContainers() {
    if (this._selected) this._loadContainers(this._selected);
  }

  async _loadContainers(agentId) {
    const grid    = $('containers-grid');
    const summary = $('containers-summary');
    grid.innerHTML = '<div class="containers-empty">Loading…</div>';
    try {
      const res  = await fetch(`/api/agents/${agentId}/containers`);
      const data = await res.json();
      if (data.error) {
        grid.innerHTML = `<div class="containers-empty">${esc(data.error)}</div>`;
        return;
      }
      const containers = data.containers || [];
      summary.textContent = `${data.running ?? 0} running · ${data.stopped ?? 0} stopped · ${data.count ?? 0} total`;
      if (!containers.length) {
        grid.innerHTML = '<div class="containers-empty">No containers found.</div>';
        return;
      }
      grid.innerHTML = containers.map(c => this._containerCard(agentId, c)).join('');
    } catch (e) {
      grid.innerHTML = `<div class="containers-empty">Failed to load: ${esc(String(e))}</div>`;
    }
  }

  _containerCard(agentId, c) {
    const isUp  = c.status?.startsWith('Up');
    const cls   = isUp ? 'running' : 'stopped';
    const cpu   = c.cpu    || '—';
    const mem   = c.memory || '—';
    const memPct = c.mem_pct || '';
    const memVal = memPct || (mem.split('/')[0]?.trim()) || '—';
    const name  = esc(c.name);
    const n     = c.name;

    return `<div class="c-card ${cls}" id="cc-${name}">
      <div class="c-hdr">
        <div class="c-name">${name}</div>
        <div class="dot ${cls}"></div>
      </div>
      <div class="c-image">${esc(c.image || '')}</div>
      <div class="c-meta">
        <div class="c-row">
          <span class="c-lbl">Status</span>
          <span class="c-val ${isUp ? 'up' : 'down'}">${esc(c.status || '—')}</span>
        </div>
        ${c.running_for ? `<div class="c-row"><span class="c-lbl">Uptime</span><span class="c-val">${esc(c.running_for)}</span></div>` : ''}
      </div>
      ${isUp ? `<div class="c-stats">
        <div class="c-chip"><div class="c-chip-val">${esc(cpu)}</div><div class="c-chip-lbl">CPU</div></div>
        <div class="c-chip"><div class="c-chip-val">${esc(memVal)}</div><div class="c-chip-lbl">Mem%</div></div>
        <div class="c-chip"><div class="c-chip-val" style="font-size:10px">${esc(mem.split('/')[0]?.trim()||'—')}</div><div class="c-chip-lbl">Mem Used</div></div>
      </div>` : ''}
      <div class="c-actions">
        <button class="c-btn start"   ${isUp  ? 'disabled' : ''} onclick="window._dash._containerAction('${agentId}','${esc(n)}','start')">Start</button>
        <button class="c-btn stop"    ${!isUp ? 'disabled' : ''} onclick="window._dash._containerAction('${agentId}','${esc(n)}','stop')">Stop</button>
        <button class="c-btn restart"                             onclick="window._dash._containerAction('${agentId}','${esc(n)}','restart')">Restart</button>
      </div>
    </div>`;
  }

  async _containerAction(agentId, containerName, action) {
    const card = document.getElementById(`cc-${containerName}`);
    card?.querySelectorAll('.c-btn').forEach(b => b.disabled = true);
    try {
      const res  = await fetch(
        `/api/agents/${agentId}/containers/${encodeURIComponent(containerName)}/${action}`,
        { method: 'POST' }
      );
      const data = await res.json();
      if (!res.ok || data.error) {
        const msg = data.detail || data.error || 'Action failed';
        const err = document.createElement('div');
        err.className = 'containers-empty';
        err.style.cssText = 'color:var(--red);font-size:12px;grid-column:1/-1;padding:4px 0';
        err.textContent = `${containerName}: ${msg}`;
        card?.insertAdjacentElement('afterend', err);
        setTimeout(() => err.remove(), 5000);
      }
    } catch (e) {
      console.error('Container action error:', e);
    }
    setTimeout(() => this._loadContainers(agentId), 2000);
  }

  // ── UI bindings ───────────────────────────────────────────────────────────

  _bindUI() {
    $('chat-in').addEventListener('keydown', e => { if (e.key === 'Enter') this.sendMsg(); });
    $('s-volume').addEventListener('input', () => {
      $('s-vol-val').textContent = $('s-volume').value + '%';
    });
  }
}

// Boot
document.addEventListener('DOMContentLoaded', () => {
  const dash = new Dashboard();
  dash.init();
});
