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
    const running = this._agents.filter(a => a.status === 'running').length;
    $('stat-running').textContent = `${running}/${this._agents.length} running`;
  }

  // ── Grid view ─────────────────────────────────────────────────────────────

  _renderGrid() {
    const grid = $('grid-view');
    if (!grid) return;
    grid.innerHTML = '';
    for (const a of this._agents) {
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
    list.innerHTML = this._agents.map(a => `
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

  showGrid() {
    this._view = 'grid';
    $('grid-view').classList.remove('hidden');
    $('detail-view').classList.add('hidden');
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
    setTimeout(() => this._fetchAgents().then(() => { this._renderGrid(); this._updateSidebar(); this._updateDetailHeader(); }), 2000);
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
