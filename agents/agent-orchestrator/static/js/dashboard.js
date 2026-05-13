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

    s.on('agent_event', data => {
      this._handleAgentEvent(data);
    });
  }

  // ── Agent telemetry events ────────────────────────────────────────────────

  _handleAgentEvent(data) {
    const event     = data.event || '';
    const source    = data.source || 'agent';
    const container = data.container || '';
    const payload   = data.data || {};

    if (event === 'user_intervention_required') {
      this._showInterventionSplash(payload.message || 'User action required', source, payload);
      return;
    }


    // Map event → toast style
    const styleMap = {
      service_started:      { cls: 'info',    icon: '⚡', label: 'Service started' },
      service_stopped:      { cls: 'warning', icon: '⏹', label: 'Service stopped' },
      install_error:        { cls: 'error',   icon: '✗',  label: 'Install error' },
      auto_resolve_complete:{ cls: 'info',    icon: '✓',  label: 'Auto-fixed' },
      auto_resolve_failed:  { cls: 'warning', icon: '⚠',  label: 'Auto-fix failed' },
      task_complete:        { cls: 'info',    icon: '✓',  label: 'Task complete' },
      status_update:        { cls: 'info',    icon: 'ℹ',  label: 'Status' },
    };
    const style = styleMap[event] || { cls: 'info', icon: 'ℹ', label: event };
    const detail = payload.summary || payload.label || payload.service || payload.error || '';
    const msg = detail ? `${style.label}: ${detail}` : style.label;
    this._showToast(msg, style.cls, source || container);
  }

  _showToast(message, cls, origin) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const el = document.createElement('div');
    el.className = `toast toast-${cls}`;
    const ts = new Date().toLocaleTimeString();
    el.innerHTML = `
      <span class="toast-origin">${esc(origin)}</span>
      <span class="toast-msg">${esc(message)}</span>
      <span class="toast-time">${ts}</span>
      <button class="toast-close" onclick="this.closest('.toast').remove()">✕</button>`;
    container.appendChild(el);
    // auto-dismiss after 6s
    setTimeout(() => { if (el.parentNode) el.remove(); }, 6000);
  }

  async _showInterventionSplash(message, source, details) {
    // read bell_rings from docker-manager config (live, no restart needed)
    let n = 5;
    try {
      const r = await fetch('http://localhost:8889/api/config');
      if (r.ok) n = (await r.json()).bell_rings || 5;
    } catch {}
    this._beepN(n);
    // splash screen
    let splash = document.getElementById('intervention-splash');
    if (!splash) {
      splash = document.createElement('div');
      splash.id = 'intervention-splash';
      document.body.appendChild(splash);
    }
    const ts = new Date().toLocaleTimeString();
    const detailText = details.details
      ? `<pre class="intervention-detail">${esc(JSON.stringify(details.details, null, 2))}</pre>`
      : '';
    splash.innerHTML = `
      <div class="intervention-box">
        <div class="intervention-icon">⚠</div>
        <div class="intervention-source">${esc(source)}</div>
        <div class="intervention-title">User Action Required</div>
        <div class="intervention-msg">${esc(message)}</div>
        ${detailText}
        <div class="intervention-time">${ts}</div>
        <button class="intervention-ack" onclick="document.getElementById('intervention-splash').remove();window._dash.sound.stop()">
          Acknowledge
        </button>
      </div>`;
    splash.classList.add('active');
  }

  _beepN(n = 5) {
    this.sound.stop();
    const ctx = this.sound._ctx();
    for (let i = 0; i < n; i++) {
      const t = ctx.currentTime + i * 0.4;
      const osc  = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'square';
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.5, t);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(t);
      osc.stop(t + 0.25);
    }
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
          <span class="card-type">${a.connector}</span>
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
          <span class="type-tag">${a.connector}</span>
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
    this._disconnectCc();
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
    const pulse = $('ws-pulse'); if (pulse) pulse.style.display = 'none';
    if (this._pulseTimer) { clearInterval(this._pulseTimer); this._pulseTimer = null; }
    this._renderGrid();
    this._updateSidebar();
    this._disconnectChat();
    this._disconnectLogs();
    this._disconnectCc();
  }

  openDetail(agentId) {
    // Disconnect live streams from previous agent before switching
    this._disconnectLogs();
    this._disconnectCc();
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

    const isSubAgent = agent.hidden && isHttp;
    const tabControls = $('tab-controls');
    if (tabControls) tabControls.style.display = isSubAgent ? '' : 'none';

    const tabContainers = $('tab-containers');
    if (tabContainers) tabContainers.style.display = hasSubs ? '' : 'none';

    const tabAgents = $('tab-agents');
    if (tabAgents) tabAgents.style.display = hasSubs ? '' : 'none';

    const tabDocs = $('tab-apidocs');
    if (tabDocs) tabDocs.style.display = isHttp && !isSubAgent ? '' : 'none';

    const isWorkspace = agentId === 'workspace';
    const tabToday = $('tab-today');
    if (tabToday)   tabToday.style.display   = isWorkspace ? '' : 'none';
    const tabGit  = $('tab-git');
    if (tabGit)     tabGit.style.display     = isWorkspace ? '' : 'none';
    const tabCon  = $('tab-console');
    if (tabCon)     tabCon.style.display     = isWorkspace ? '' : 'none';
    const tabCC   = $('tab-claudecode');
    if (tabCC)      tabCC.style.display      = isWorkspace ? '' : 'none';
    const tabProj = $('tab-projects');
    if (tabProj)    tabProj.style.display    = isWorkspace ? '' : 'none';

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

    if (agentId === 'workspace') {
      this.switchTab('today');
      this._loadToday();
      this._loadPulse();
      if (this._pulseTimer) clearInterval(this._pulseTimer);
      this._pulseTimer = setInterval(() => this._loadPulse(), 30000);
    } else if (isSubAgent) {
      this.switchTab('controls');
      if (this._pulseTimer) { clearInterval(this._pulseTimer); this._pulseTimer = null; }
    } else {
      this.switchTab('chat');
      if (this._pulseTimer) { clearInterval(this._pulseTimer); this._pulseTimer = null; }
    }
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
    if (name === 'controls'   && this._selected) this._loadControls(this._selected);
    if (name === 'containers' && this._selected) this._loadContainers(this._selected);
    if (name === 'agents'    && this._selected) this._loadSubAgents(this._selected);
    if (name === 'today'     && this._selected) this._loadToday();
    if (name === 'git')        this._gitLoadRepos();
    if (name === 'console')    this._consoleInit();
    if (name === 'claudecode') { this._ccInit(); setTimeout(() => this._ccScrollBottom(), 300); }
    if (name === 'projects')   this._loadProjects();
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

  _disconnectCc() {
    if (this._ccEs) { this._ccEs.close(); this._ccEs = null; }
  }

  // ── Git panel ─────────────────────────────────────────────────────────────

  async _completeTodo(id) {
    const row = document.getElementById(`todo-row-${id}`);
    if (row) row.style.opacity = '0.4';
    try {
      const res = await fetch(`/api/agents/workspace/todos/${id}/complete`, { method: 'POST' });
      const d   = await res.json();
      if (d.ok) {
        if (row) row.remove();
        // refresh today panel counts
        this._loadToday();
      } else {
        if (row) row.style.opacity = '1';
      }
    } catch (_) {
      if (row) row.style.opacity = '1';
    }
  }

  _gitJumpTo(repoPath) {
    // Switch to git tab and select this repo
    this.switchTab('git');
    const sel = $('git-repo-sel');
    if (sel) {
      // If repo is already in list, select it; else reload and then select
      const opt = [...sel.options].find(o => o.value === repoPath);
      if (opt) { sel.value = repoPath; this._gitRefresh(); }
      else { this._gitLoadRepos().then(() => { if (sel) { sel.value = repoPath; this._gitRefresh(); } }); }
    }
  }

  _gitActiveRepo() {
    return $('git-repo-sel')?.value || '';
  }

  async _gitLoadRepos() {
    const sel = $('git-repo-sel');
    if (!sel) return;
    try {
      const res   = await fetch('/api/git/repos').catch(() => null);
      if (!res || !res.ok) { sel.innerHTML = '<option value="">No repos found</option>'; return; }
      const d     = await res.json();
      const repos = d.repos || [];
      if (!repos.length) { sel.innerHTML = '<option value="">No git repos in projectspace</option>'; return; }
      sel.innerHTML = repos.map(r => {
        let hint = '';
        if (r.changed)       hint += `  · ${r.changed} changed`;
        if (r.ahead  > 0)    hint += `  ↑${r.ahead} to push`;
        if (r.behind > 0)    hint += `  ↓${r.behind} to pull`;
        if (!r.has_remote)   hint += '  (no remote)';
        return `<option value="${esc(r.path)}">${esc(r.name)}  [${esc(r.branch)}]${hint}</option>`;
      }).join('');
    } catch (_) {
      sel.innerHTML = '<option value="">Failed to load repos</option>';
    }
    this._gitRefresh();
  }

  async _gitRefresh() {
    const fileList = $('git-file-list');
    const logEl    = $('git-log');
    const out      = $('git-output');
    if (!fileList) return;
    fileList.innerHTML = '<div class="git-loading">Loading…</div>';
    const repo = this._gitActiveRepo();
    try {
      const url  = '/api/git/status' + (repo ? `?repo=${encodeURIComponent(repo)}` : '');
      const res  = await fetch(url).catch(() => null);
      if (!res || !res.ok) { fileList.innerHTML = '<div class="git-loading">Git unavailable</div>'; return; }
      const d    = await res.json();
      if (d.error) { fileList.innerHTML = `<div class="git-loading">${esc(d.error)}</div>`; return; }

      // Branch badge
      const badge = $('git-branch-badge');
      if (badge) badge.textContent = '⎇ ' + (d.branch || '?');

      // Ahead / behind remote
      const aheadBadge = $('git-ahead-badge');
      if (aheadBadge) {
        if (!d.has_remote) {
          aheadBadge.style.display = '';
          aheadBadge.textContent   = 'no remote';
          aheadBadge.className     = 'git-ahead-badge git-no-remote';
        } else if (d.ahead > 0 || d.behind > 0) {
          aheadBadge.style.display = '';
          let txt = '';
          if (d.ahead  > 0) txt += `↑${d.ahead} to push`;
          if (d.behind > 0) txt += (txt ? '  ' : '') + `↓${d.behind} to pull`;
          aheadBadge.textContent   = txt;
          aheadBadge.className     = 'git-ahead-badge' + (d.ahead > 0 ? ' git-ahead-has' : ' git-behind-has');
        } else {
          aheadBadge.style.display = '';
          aheadBadge.textContent   = '✓ up to date';
          aheadBadge.className     = 'git-ahead-badge git-synced';
        }
      }

      // File list
      this._gitFiles = d.files || [];
      fileList.innerHTML = this._gitFiles.length
        ? this._gitFiles.map((f, i) => {
            const big  = (f.size_bytes || 0) >= 1_048_576;
            const warn = (f.size_bytes || 0) >= 10_485_760; // 10 MB warning
            const sizeHtml = f.size
              ? `<span class="git-file-size${warn ? ' git-file-size-warn' : big ? ' git-file-size-big' : ''}">${esc(f.size)}</span>`
              : '';
            return `
            <div class="git-file-row${warn ? ' git-file-row-warn' : ''}" data-idx="${i}">
              <input type="checkbox" class="git-file-cb" id="gf${i}" ${f.state === 'staged' ? 'checked' : ''}>
              <span class="git-file-st git-st-${esc(f.state)}">${esc(f.status)}</span>
              <label class="git-file-path" for="gf${i}">${esc(f.path)}</label>
              ${sizeHtml}
            </div>`;
          }).join('')
        : `<div class="git-clean">Working tree clean ✓${
            !d.has_remote   ? ' — <span style="color:var(--text3)">no remote configured</span>' :
            d.ahead > 0     ? ` — <span style="color:var(--yellow)">↑${d.ahead} commit${d.ahead>1?'s':''} not pushed yet</span>` :
            d.behind > 0    ? ` — <span style="color:var(--blue)">↓${d.behind} commit${d.behind>1?'s':''} to pull</span>` : ''
          }</div>`;

      // Stat breakdown bar
      const statBar   = $('git-stat-bar');
      if (statBar) {
        const staged    = this._gitFiles.filter(f => f.state === 'staged').length;
        const modified  = this._gitFiles.filter(f => f.state === 'modified').length;
        const untracked = this._gitFiles.filter(f => f.state === 'untracked').length;
        const total     = staged + modified + untracked;
        if (total > 0) {
          const seg = (n, clr) => n ? `<div class="git-stat-seg" style="width:${(n/total*100).toFixed(1)}%;background:${clr}" title="${n}"></div>` : '';
          const lbl = (n, clr, t) => n ? `<span style="color:${clr}">■ ${n} ${t}</span>` : '';
          statBar.style.display = '';
          statBar.innerHTML = `
            <div class="git-stat-segs">
              ${seg(staged,'#3fb950')}${seg(modified,'#58a6ff')}${seg(untracked,'#d29922')}
            </div>
            <div class="git-stat-legend">
              ${lbl(staged,'#3fb950','staged')}${lbl(modified,'#58a6ff','modified')}${lbl(untracked,'#d29922','untracked')}
            </div>`;
        } else {
          statBar.style.display = 'none';
        }
      }

      // Log
      if (logEl) {
        logEl.innerHTML = d.log
          ? d.log.split('\n').map(l => `<div class="git-log-line">${esc(l)}</div>`).join('')
          : '<div class="git-loading">No commits yet</div>';
      }
      if (out) out.textContent = '';
    } catch (e) {
      if (fileList) fileList.innerHTML = `<div class="git-loading">Error: ${esc(String(e))}</div>`;
    }
  }

  _gitCheckedFiles() {
    const checked = [];
    document.querySelectorAll('.git-file-cb:checked').forEach((cb, _) => {
      const idx = parseInt(cb.closest('.git-file-row')?.dataset.idx ?? '-1');
      if (idx >= 0 && this._gitFiles?.[idx]) checked.push(this._gitFiles[idx].path);
    });
    return checked;
  }

  async _gitPost(endpoint, body = {}) {
    // Duplicate guard: ignore same git action within 2 seconds
    const key = endpoint + JSON.stringify(body);
    const now = Date.now();
    if (key === this._lastGitKey && now - (this._lastGitTs||0) < 2000) return;
    this._lastGitKey = key;
    this._lastGitTs  = now;

    const out = $('git-output');
    if (out) { out.className = 'git-output'; out.textContent = '…'; }
    try {
      const res  = await fetch(endpoint, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      const d    = await res.json();
      if (out) {
        out.className  = 'git-output ' + (d.ok ? 'ok' : 'err');
        out.textContent = d.output || (d.ok ? 'Done' : 'Failed');
      }
      if (d.ok) this._gitRefresh();
      return d;
    } catch (e) {
      if (out) { out.className = 'git-output err'; out.textContent = String(e); }
    }
  }

  async _gitAddAll()   { await this._gitPost('/api/git/add-all', { repo: this._gitActiveRepo() }); }
  async _gitPush()     { await this._gitPost('/api/git/push',    { repo: this._gitActiveRepo() }); }
  async _gitPull()     { await this._gitPost('/api/git/pull',    { repo: this._gitActiveRepo() }); }

  async _gitCommit() {
    const msg = $('git-commit-msg')?.value?.trim();
    if (!msg) { const o = $('git-output'); if (o) { o.className='git-output err'; o.textContent='Enter a commit message'; } return; }
    const files = this._gitCheckedFiles();
    const d = await this._gitPost('/api/git/commit', { message: msg, files, repo: this._gitActiveRepo() });
    if (d?.ok && $('git-commit-msg')) $('git-commit-msg').value = '';
  }

  // ── Console panel ──────────────────────────────────────────────────────────

  async _consoleInit() {
    const sel = $('console-cwd');
    if (!sel || sel.dataset.loaded) return;
    sel.dataset.loaded = '1';
    try {
      const res = await fetch('/api/console/cwd-list').catch(() => null);
      if (!res) return;
      const d   = await res.json();
      sel.innerHTML = ['', ...(d.dirs || [])].map(dir =>
        `<option value="${esc(dir)}">${dir || '/ workspace root'}</option>`
      ).join('');
    } catch (_) {}
    // Enter key
    const inp = $('console-input');
    if (inp) inp.addEventListener('keydown', e => { if (e.key === 'Enter') this._consoleRun(); });
  }

  async _consoleRun() {
    const inp = $('console-input');
    const sel = $('console-cwd');
    const out = $('console-output');
    if (!inp || !out) return;
    const cmd = inp.value.trim();
    if (!cmd) return;

    const cwd = sel?.value || '';

    // Duplicate guard: ignore identical command+cwd within 3 seconds
    const dedupeKey = `${cwd}:${cmd}`;
    const now = Date.now();
    if (dedupeKey === this._lastConsoleKey && now - (this._lastConsoleTs||0) < 3000) return;
    this._lastConsoleKey = dedupeKey;
    this._lastConsoleTs  = now;

    // Echo the command
    const header = document.createElement('div');
    header.className = 'con-cmd';
    header.textContent = `${cwd ? cwd + '/' : ''}$ ${cmd}`;
    out.appendChild(header);

    inp.value    = '';
    inp.disabled = true;

    try {
      const res  = await fetch('/api/console/exec', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ command: cmd, cwd })
      });
      const d    = await res.json();
      const body = document.createElement('pre');
      body.className = 'con-out ' + (d.ok ? 'ok' : 'err');
      body.textContent = d.output || (d.ok ? '(no output)' : 'Command failed');
      if (!d.ok) body.textContent += `\n[exit ${d.exit_code}]`;
      out.appendChild(body);
    } catch (e) {
      const err = document.createElement('pre');
      err.className   = 'con-out err';
      err.textContent = String(e);
      out.appendChild(err);
    }

    inp.disabled = false;
    inp.focus();
    out.scrollTop = out.scrollHeight;
  }

  _consoleClear() {
    const out = $('console-output');
    if (out) out.innerHTML = '';
  }

  // ── Claude Code memory feed ───────────────────────────────────────────────

  _ccInit() {
    if (this._ccEs) return;              // already connected
    const feed  = $('cc-feed');
    const label = $('cc-live-label');
    const dot   = $('cc-live-dot');
    if (!feed) return;

    this._ccSeen  = new Set();           // track IDs to avoid duplicates
    this._ccTotal = 0;

    this._ccEs = new EventSource('/api/claude-code/stream');

    this._ccEs.onopen = () => {
      if (dot)   { dot.className = 'cc-live-dot live'; }
      if (label) label.textContent = 'Live — reading memory…';
    };

    this._ccEs.onmessage = (e) => {
      if (!e.data || e.data.startsWith(':')) return;
      try {
        const ex = JSON.parse(e.data);
        if (!ex.id || this._ccSeen.has(+ex.id)) return;
        this._ccSeen.add(+ex.id);
        this._ccTotal++;
        this._ccAppend(ex);
        if ($('cc-count')) $('cc-count').textContent = `${this._ccTotal} exchanges in memory`;
        if (dot)   dot.className = 'cc-live-dot live';
        if (label) label.textContent = `Live · last update ${new Date().toLocaleTimeString()}`;
      } catch (_) {}
    };

    this._ccEs.onerror = () => {
      if (dot)   dot.className = 'cc-live-dot';
      if (label) label.textContent = 'Reconnecting…';
    };
  }

  _ccAppend(ex) {
    const feed = $('cc-feed');
    if (!feed) return;

    const prompt = (ex.prompt || '').trim();
    if (!prompt || prompt.startsWith('<')) return;  // skip system noise

    const div  = document.createElement('div');
    div.className = 'cc-exchange';
    div.dataset.id = ex.id;

    const ts   = (ex.timestamp || '').slice(0, 16).replace('T', ' ');
    const resp = (ex.response || '').trim();

    div.innerHTML = `
      <div class="cc-ts">${esc(ts)}</div>
      <div class="cc-user-wrap">
        <div class="cc-bubble">
          <div class="cc-bubble-label">You</div>
          <div class="cc-bubble-text">${esc(prompt.slice(0, 600))}${prompt.length > 600 ? '\n…' : ''}</div>
        </div>
      </div>
      ${resp ? `
      <div class="cc-assistant-wrap">
        <div class="cc-bubble">
          <div class="cc-bubble-label">Claude</div>
          <div class="cc-bubble-text">${esc(resp.slice(0, 1200))}${resp.length > 1200 ? '\n…' : ''}</div>
        </div>
      </div>
      <div class="cc-memory-tag">✓ in memory</div>` :
      `<div class="cc-no-response">response pending next scan…</div>`}`;

    feed.appendChild(div);
  }

  async _ccScrollBottom() {
    // Pull any new exchanges immediately, then scroll
    const feed = $('cc-feed');
    if (!feed) return;
    const lastId = this._ccSeen.size ? Math.max(...this._ccSeen) : 0;
    try {
      const res = await fetch(`/api/claude-code/history?limit=50&after_id=${lastId}`).catch(() => null);
      if (res && res.ok) {
        const d = await res.json();
        for (const ex of (d.exchanges || [])) {
          if (!this._ccSeen.has(+ex.id)) {
            this._ccSeen.add(+ex.id);
            this._ccTotal++;
            this._ccAppend(ex);
          }
        }
        if ($('cc-count')) $('cc-count').textContent = `${this._ccTotal} exchanges in memory`;
      }
    } catch (_) {}
    feed.scrollTop = feed.scrollHeight;
  }

  _ccClear() {
    // Only clears the visual view — DB memory is untouched
    const feed = $('cc-feed');
    if (feed) {
      feed.innerHTML = '<div style="color:var(--text3);font-size:11px;padding:20px;text-align:center">View cleared — DB memory preserved. New entries will appear as they arrive.</div>';
      this._ccSeen  = new Set();
      this._ccTotal = 0;
    }
    // Reconnect SSE to reload history
    if (this._ccEs) { this._ccEs.close(); this._ccEs = null; }
    setTimeout(() => this._ccInit(), 500);
  }

  // ── Workspace pulse bar ───────────────────────────────────────────────────

  async _loadPulse() {
    const bar   = $('ws-pulse');
    const pills = $('ws-pulse-pills');
    if (!bar || !pills) return;
    try {
      const res  = await fetch('/api/agents/workspace/memory/today.json').catch(() => null);
      if (!res || !res.ok) return;
      const data    = await res.json();
      const content = JSON.parse(data.content || '{}');
      const sugs    = content.suggestions || [];

      if (sugs.length === 0) {
        bar.style.display = '';
        pills.innerHTML   = '<span class="ws-pill info">All clear ✓</span>';
        bar.className     = 'ws-pulse ws-pulse-clear';
        return;
      }

      const hasEmergency = sugs.some(s => s.level === 'emergency');
      const hasWarning   = sugs.some(s => s.level === 'warning');
      bar.className      = `ws-pulse ${hasEmergency ? 'ws-pulse-emergency' : hasWarning ? 'ws-pulse-warning' : 'ws-pulse-info'}`;
      bar.style.display  = '';

      pills.innerHTML = sugs.slice(0, 6).map(s =>
        `<span class="ws-pill ${esc(s.level)}" title="${esc(s.source)}">${esc(s.message)}</span>`
      ).join('');
    } catch (e) { /* silent */ }
  }

  _refreshPulse() { this._loadPulse(); this._loadToday(); }

  // ── Today panel (workspace agent) ────────────────────────────────────────

  async _loadToday() {
    const wrap = $('today-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<div class="today-loading">Loading…</div>';
    try {
      const res  = await fetch('/api/agents/workspace/memory/today.json').catch(() => null);
      if (!res || !res.ok) { wrap.innerHTML = '<div class="today-loading">today.json not ready yet — scanner runs every 30s.</div>'; return; }
      const data = await res.json();
      const content = JSON.parse(data.content || '{}');
      wrap.innerHTML = this._renderToday(content);
      // Sync git repo selector if git tab is loaded and today has fresh repos
      if (content.git_repos?.length) this._gitSyncRepos(content.git_repos);
    } catch (e) {
      wrap.innerHTML = `<div class="today-loading">Error: ${esc(String(e))}</div>`;
    }
  }

  _gitSyncRepos(repos) {
    const sel = $('git-repo-sel');
    if (!sel) return;
    const current = sel.value;
    sel.innerHTML = repos.map(r => {
      let hint = '';
      if (r.changed)     hint += `  · ${r.changed} changed`;
      if (r.ahead  > 0)  hint += `  ↑${r.ahead} to push`;
      if (r.behind > 0)  hint += `  ↓${r.behind} to pull`;
      if (!r.has_remote) hint += '  (no remote)';
      return `<option value="${esc(r.path)}" ${r.path === current ? 'selected' : ''}>${esc(r.name)}  [${esc(r.branch)}]${hint}</option>`;
    }).join('');
    // If current selection was lost (repo removed), refresh git panel
    if (current && sel.value !== current) this._gitRefresh();
  }

  _renderToday(d) {
    const ts     = d.generated_at ? `<span class="today-ts">Updated ${esc(d.generated_at)}</span>` : '';
    const stats  = d.scan_stats   ? `${d.scan_stats.files} files · ${d.scan_stats.dirs} dirs · ${d.file_counts?.history_events||d.scan_stats.history_events||0} changes logged` : '';

    // Todos
    const todos  = (d.todos || []);
    const prioIcon = p => p === 'urgent' ? '🔴' : p === 'high' ? '🟠' : p === 'normal' ? '🟡' : '⚪';
    const todoRows = todos.length
      ? todos.map(t => `<div class="today-todo-item" id="todo-row-${t.id}">
          <span class="today-todo-prio">${prioIcon(t.priority)}</span>
          <span class="today-todo-text">${esc(t.text)}</span>
          <span class="today-todo-meta">#${t.id} · ${esc(t.source||'manual')} · ${esc((t.created_at||'').slice(0,10))}</span>
          <button class="today-todo-done" onclick="window._dash._completeTodo(${t.id})" title="Mark done">✓</button>
        </div>`).join('')
      : '<div class="today-empty">No open tasks — you\'re clear ✓</div>';

    // Todo priority breakdown bar
    const prioCounts = {urgent:0, high:0, normal:0, low:0};
    todos.forEach(t => { const k = t.priority||'low'; prioCounts[k] = (prioCounts[k]||0)+1; });
    const prioTotal = todos.length || 1;
    const prioSeg = (n, clr) => n ? `<div class="today-prio-seg" style="width:${(n/prioTotal*100).toFixed(1)}%;background:${clr}"></div>` : '';
    const prioLbl = (n, clr, t) => n ? `<span style="color:${clr}">● ${n} ${t}</span>` : '';
    const prioBar = todos.length ? `
      <div class="today-prio-bar">
        ${prioSeg(prioCounts.urgent,'#f85149')}${prioSeg(prioCounts.high,'#d29922')}${prioSeg(prioCounts.normal,'#58a6ff')}${prioSeg(prioCounts.low,'#3fb950')}
      </div>
      <div class="today-prio-legend">
        ${prioLbl(prioCounts.urgent,'#f85149','urgent')}${prioLbl(prioCounts.high,'#d29922','high')}${prioLbl(prioCounts.normal,'#58a6ff','normal')}${prioLbl(prioCounts.low,'#3fb950','low')}
      </div>` : '';

    // Activity sparkline — group all changes by hour
    const allChanges  = (d.recent_changes || []);
    const hrBuckets   = new Array(24).fill(0);
    allChanges.forEach(c => {
      const h = parseInt((c.timestamp||'').slice(11,13)||'0', 10);
      if (!isNaN(h) && h >= 0 && h < 24) hrBuckets[h]++;
    });
    const maxH    = Math.max(...hrBuckets, 1);
    const svgW    = 280, svgH = 24, bw = svgW / 24 - 1;
    const sparkBars = hrBuckets.map((v, i) => {
      const bh   = v > 0 ? Math.max((v / maxH) * (svgH - 2), 3) : 1;
      const x    = (i * svgW / 24).toFixed(1);
      const y    = (svgH - bh).toFixed(1);
      const fill = v > 0 ? '#58a6ff' : '#21262d';
      return `<rect x="${x}" y="${y}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" fill="${fill}" rx="1"/>`;
    }).join('');
    const nowH    = new Date().getHours();
    const sparkline = `
      <div class="today-spark-wrap">
        <div class="today-spark-lbl"><span>File activity by hour (0h–23h)</span><span>now: ${nowH}h · ${allChanges.length} events</span></div>
        <svg class="today-spark" viewBox="0 0 ${svgW} ${svgH}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">${sparkBars}</svg>
      </div>`;

    // Recent changes (list, last 10)
    const changes = allChanges.slice(0, 10);
    const changeRows = changes.length
      ? changes.map(c => `<div class="today-change-item">
          <span class="today-change-ev ${esc(c.event)}">${esc(c.event)}</span>
          <span class="today-change-path">${esc(c.path)}</span>
          <span class="today-change-ts">${esc((c.timestamp||'').slice(11,16))}</span>
        </div>`).join('')
      : '<div class="today-empty">No recent changes</div>';

    // Git repos (dynamically discovered from projectspace)
    const gitRepos  = (d.git_repos || []);

    // Templates / projects
    const templates = (d.templates || []);
    const projRows  = (gitRepos.length || templates.length)
      ? [
          ...gitRepos.map(r => {
            let badges = '';
            if (r.changed)     badges += `<span class="today-git-badge today-git-changed">${r.changed} changed</span>`;
            if (r.ahead  > 0)  badges += `<span class="today-git-badge today-git-ahead">↑${r.ahead} to push</span>`;
            if (r.behind > 0)  badges += `<span class="today-git-badge today-git-behind">↓${r.behind} to pull</span>`;
            if (!r.has_remote) badges += `<span class="today-git-badge today-git-noremote">no remote</span>`;
            return `<div class="today-proj-item">
              <span class="today-proj-type git-repo-badge">git</span>
              <span class="today-proj-path">${esc(r.name)}</span>
              <span class="today-proj-branch">[${esc(r.branch)}]</span>
              ${badges}
              <button class="today-proj-open git-btn" style="font-size:9px;padding:1px 5px" onclick="window._dash._gitJumpTo('${esc(r.path)}')">Open</button>
            </div>`;
          }),
          ...templates.map(t => `<div class="today-proj-item">
            <span class="today-proj-type">${esc(t.project_type)}</span>
            <span class="today-proj-path">${esc(t.root_path)}</span>
          </div>`),
        ].join('')
      : '<div class="today-empty">No projects detected</div>';

    // Knowledge
    const knowledge = (d.recent_knowledge || []).slice(0, 5);
    const knowRows  = knowledge.length
      ? knowledge.map(k => `<div class="today-know-item">
          <span class="today-know-cat">${esc(k.category)}</span>
          <span class="today-know-title">${esc(k.title)}</span>
        </div>`).join('')
      : '<div class="today-empty">No knowledge entries yet — ask the agent to save observations</div>';

    // Prompt history
    const prompts   = (d.prompt_history || []);
    const promptRows = prompts.length
      ? prompts.map(p => `<div class="today-prompt-item">
          <span class="today-prompt-ts">${esc((p.timestamp||'').slice(0,16).replace('T',' '))}</span>
          <span class="today-prompt-text">${esc((p.prompt||'').slice(0,120))}</span>
        </div>`).join('')
      : '<div class="today-empty">No prompt history yet</div>';

    return `
      <div class="today-header">${ts}<span class="today-stats">${stats}</span></div>
      <div class="today-grid">
        <div class="today-section">
          <div class="today-section-title">📋 Open Tasks (${todos.length})</div>
          ${prioBar}
          <div class="today-section-body">${todoRows}</div>
        </div>
        <div class="today-section">
          <div class="today-section-title">📁 Active Projects (${templates.length})</div>
          <div class="today-section-body today-projs">${projRows}</div>
        </div>
        <div class="today-section today-wide">
          <div class="today-section-title">🕐 Recent Changes</div>
          ${sparkline}
          <div class="today-section-body">${changeRows}</div>
        </div>
        <div class="today-section">
          <div class="today-section-title">🧠 Knowledge Base</div>
          <div class="today-section-body">${knowRows}</div>
        </div>
        <div class="today-section">
          <div class="today-section-title">💬 Prompt History</div>
          <div class="today-section-body">${promptRows}</div>
        </div>
      </div>`;
  }

  // ── Memory ────────────────────────────────────────────────────────────────

  async _loadMemory(agentId) {
    const res  = await fetch(`/api/agents/${agentId}/memory`).catch(() => null);
    if (!res) return;
    const data = await res.json();
    const list = $('mem-list');
    list.innerHTML = '';
    for (const f of (data.files || [])) {
      const name = typeof f === 'string' ? f : f.name;
      const size = typeof f === 'object' ? f.size : null;
      const div = document.createElement('div');
      div.className = 'mem-item';
      div.innerHTML = `<span class="mem-item-name">${esc(name)}</span>${size ? `<span class="mem-item-size">${esc(size)}</span>` : ''}`;
      div.onclick = () => this._openMemFile(agentId, name, div);
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

  // ── Controls pane (sub-agent health + service buttons) ───────────────────

  async _loadControls(agentId) {
    const wrap = $('controls-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<div class="controls-loading">Fetching health…</div>';
    try {
      const fetches = [fetch(`/api/agents/${agentId}/health`)];
      if (agentId === 'db-agent') fetches.push(fetch(`/api/agents/${agentId}/services`));
      const results  = await Promise.all(fetches);
      const h        = await results[0].json();
      const svcData  = results[1] ? await results[1].json() : {};
      const services = svcData.services || {};

      if (h.error) { wrap.innerHTML = `<div class="controls-loading" style="color:var(--danger)">${esc(h.error)}</div>`; return; }

      const issues = h.issues || [];
      const issueHtml = issues.length
        ? `<div class="ctrl-issues">${issues.map(i => `<div class="ctrl-issue-row">⚠ ${esc(i)}</div>`).join('')}</div>`
        : `<div class="ctrl-ok-row">✓ No active issues</div>`;

      const skip = new Set(['status', 'issues', 'time', 'agent']);
      const fields = Object.entries(h).filter(([k]) => !skip.has(k));
      const fieldsHtml = fields.map(([k, v]) => {
        const valStr = typeof v === 'boolean' ? (v ? 'Yes' : 'No') : String(v);
        const valCls = typeof v === 'boolean' ? (v ? 'green' : 'red') : '';
        return `<div class="ctrl-field"><span class="ctrl-field-lbl">${esc(k.replace(/_/g,' '))}</span><span class="ctrl-field-val ${valCls}">${esc(valStr)}</span></div>`;
      }).join('');

      const buttons = this._controlButtons(agentId, h, services);

      wrap.innerHTML = `
        <div class="controls-header">
          <span class="ctrl-agent-lbl">${esc(h.agent || agentId)}</span>
          <span class="ctrl-status ${issues.length ? 'degraded' : 'ok'}">${issues.length ? 'Degraded' : 'Healthy'}</span>
          <button class="ctrl-refresh-btn" onclick="window._dash._loadControls('${agentId}')">↺ Refresh</button>
        </div>
        <div class="ctrl-fields">${fieldsHtml}</div>
        <div class="ctrl-section-lbl">Issues</div>
        ${issueHtml}
        ${buttons ? `<div class="ctrl-section-lbl">Service Controls</div><div class="ctrl-btns">${buttons}</div>` : ''}`;
    } catch (e) {
      wrap.innerHTML = `<div class="controls-loading" style="color:var(--danger)">Failed: ${esc(String(e))}</div>`;
    }
  }

  _controlButtons(agentId, health, services = {}) {
    if (agentId === 'db-agent') {
      const pgUp = health.postgres_running;
      let html = `
        <button class="ctrl-btn start" ${pgUp  ? 'disabled' : ''} onclick="window._dash._controlAction('db-agent','api/db/start')">▶ PostgreSQL</button>
        <button class="ctrl-btn stop"  ${!pgUp ? 'disabled' : ''} onclick="window._dash._controlAction('db-agent','api/db/stop')">■ PostgreSQL</button>
        <button class="ctrl-btn init"  ${!pgUp ? 'disabled' : ''} onclick="window._dash._controlAction('db-agent','api/initdb/umsdb')"    title="Create umsdb user + database">⚙ Init umsdb</button>
        <button class="ctrl-btn init"  ${!pgUp ? 'disabled' : ''} onclick="window._dash._controlAction('db-agent','api/initdb/mydocsdb')" title="Create mydocsdb user + database">⚙ Init mydocsdb</button>`;
      const webUp = health.pgweb_running;
      html += `
        <button class="ctrl-btn start" ${webUp  ? 'disabled' : ''} onclick="window._dash._controlAction('db-agent','api/dbui/start')" title="Start pgweb DB browser on :8085">▶ DB UI</button>
        <button class="ctrl-btn stop"  ${!webUp ? 'disabled' : ''} onclick="window._dash._controlAction('db-agent','api/dbui/stop')"  title="Stop pgweb">■ DB UI</button>`;
      for (const [key, svc] of Object.entries(services)) {
        const [proj, name] = key.split('/');
        const label = (svc.name || name).replace(/_/g, ' ');
        html += `
        <button class="ctrl-btn start" onclick="window._dash._controlAction('db-agent','api/services/${proj}/${name}/start')">▶ ${esc(label)}</button>
        <button class="ctrl-btn stop"  onclick="window._dash._controlAction('db-agent','api/services/${proj}/${name}/stop')">■ ${esc(label)}</button>`;
      }
      return html;
    }
    if (agentId === 'ums-agent') {
      return `
        <button class="ctrl-btn start" onclick="window._dash._controlAction('ums-agent','api/ums/start')">▶ Start UMS</button>
        <button class="ctrl-btn stop"  onclick="window._dash._controlAction('ums-agent','api/ums/stop')">■ Stop UMS</button>`;
    }
    return '';
  }

  async _controlAction(agentId, path) {
    const wrap = $('controls-wrap');
    const btns = wrap?.querySelectorAll('.ctrl-btn');
    btns?.forEach(b => b.disabled = true);
    try {
      const res  = await fetch(`/api/agents/${agentId}/action/${path}`, { method: 'POST' });
      const data = await res.json();
      const ok   = data.success !== false && !data.error;
      const msg  = data.output || data.error || (ok ? 'Done' : 'Failed');
      const note = document.createElement('div');
      note.className = `ctrl-action-result ${ok ? 'ok' : 'err'}`;
      note.textContent = msg.slice(0, 300);
      wrap.appendChild(note);
      setTimeout(() => note.remove(), 6000);
    } catch (e) {
      const note = document.createElement('div');
      note.className = 'ctrl-action-result err';
      note.textContent = String(e);
      wrap?.appendChild(note);
      setTimeout(() => note.remove(), 6000);
    }
    setTimeout(() => this._loadControls(agentId), 2000);
  }

  // ── Projects tab (workspace agent only) ──────────────────────────────────

  async _loadProjects() {
    const list = $('projects-list');
    if (!list) return;
    list.innerHTML = '<div class="projects-loading">Loading…</div>';
    try {
      const res  = await fetch('/api/workspace/projects');
      const data = await res.json();
      const projects = data.projects || [];
      if (!projects.length) {
        list.innerHTML = '<div class="projects-loading">No projects found in projectspace/.</div>';
        return;
      }
      list.innerHTML = projects.map(p => {
        const runCls    = p.running ? 'running' : 'stopped';
        const startDis  = p.running || !p.start_script  ? 'disabled' : '';
        const stopDis   = !p.running || !p.stop_script  ? 'disabled' : '';
        const scriptShort = p.start_script
          ? p.start_script.replace(/.*projectspace\//, '')
          : '— no start script';
        return `
        <div class="proj-card" id="proj-card-${esc(p.name)}">
          <div class="proj-card-header">
            <div class="proj-card-info">
              <span class="proj-status-dot ${runCls}"></span>
              <span class="proj-name">${esc(p.name)}</span>
            </div>
            <span class="proj-script-path">${esc(scriptShort)}</span>
          </div>
          <div class="proj-card-actions">
            <button class="ctrl-btn start" ${startDis}
              onclick="window._dash._projectStart('${esc(p.name)}')">▶ Start</button>
            <button class="ctrl-btn stop" ${stopDis}
              onclick="window._dash._projectStop('${esc(p.name)}')">■ Stop</button>
          </div>
        </div>`;
      }).join('');
    } catch (e) {
      list.innerHTML = `<div class="projects-loading" style="color:var(--danger)">Failed: ${esc(String(e))}</div>`;
    }
  }

  async _projectStart(name) {
    // Abort any existing log stream (without hiding the panel)
    if (this._projectLogCtrl) { this._projectLogCtrl.abort(); this._projectLogCtrl = null; }

    // Disable Start button immediately
    const card = document.getElementById(`proj-card-${name}`);
    const startBtn = card?.querySelector('.ctrl-btn.start');
    if (startBtn) startBtn.disabled = true;

    // Show log panel
    const logWrap  = $('project-log-wrap');
    const logDiv   = $('project-log');
    const logTitle = $('project-log-title');
    if (logDiv)   logDiv.innerHTML     = '';
    if (logTitle) logTitle.textContent = `${name} — starting…`;
    if (logWrap)  logWrap.style.display = '';

    try {
      const res  = await fetch(`/api/workspace/projects/${name}/start`, { method: 'POST' });
      const data = await res.json();
      if (!data.ok) {
        if (logDiv) logDiv.innerHTML = `<div class="proj-log-line err">${esc(data.error || 'Failed to start')}</div>`;
        if (startBtn) startBtn.disabled = false;
        return;
      }
      if (logTitle) logTitle.textContent = `${name} — log`;
    } catch (e) {
      if (logDiv) logDiv.innerHTML = `<div class="proj-log-line err">${esc(String(e))}</div>`;
      if (startBtn) startBtn.disabled = false;
      return;
    }

    // Stream log output — refresh list when script exits (gets real container state)
    await this._streamProjectLog(name);
    this._loadProjects();
  }

  async _streamProjectLog(name) {
    const logDiv = $('project-log');
    if (!logDiv) return;
    this._projectLogCtrl = new AbortController();
    try {
      const res = await fetch(`/api/workspace/projects/${name}/log`,
        { signal: this._projectLogCtrl.signal });
      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let partial = '';

      const append = text => {
        if (!text) return;
        const el = document.createElement('div');
        el.className = 'proj-log-line';
        el.textContent = text;
        logDiv.appendChild(el);
        logDiv.scrollTop = logDiv.scrollHeight;
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        partial += decoder.decode(value, { stream: true });
        const chunks = partial.split('\n\n');
        partial = chunks.pop();
        for (const chunk of chunks) {
          if (!chunk.startsWith('data: ')) continue;
          const line = chunk.slice(6);
          if (line === '__done__') { reader.cancel(); return; }
          append(line);
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError' && logDiv) {
        const el = document.createElement('div');
        el.className = 'proj-log-line err';
        el.textContent = String(e);
        logDiv.appendChild(el);
      }
    }
  }

  async _projectStop(name) {
    const logWrap  = $('project-log-wrap');
    const logDiv   = $('project-log');
    const logTitle = $('project-log-title');
    if (logWrap)  logWrap.style.display  = '';
    if (logTitle) logTitle.textContent   = `${name} — stopping…`;
    if (logDiv)   logDiv.innerHTML       = '';
    this._projectCloseLog();
    try {
      const res  = await fetch(`/api/workspace/projects/${name}/stop`, { method: 'POST' });
      const data = await res.json();
      const el   = document.createElement('div');
      el.className = data.ok ? 'proj-log-line' : 'proj-log-line err';
      el.textContent = data.output || data.error || (data.ok ? 'Stopped' : 'Failed');
      if (logDiv) logDiv.appendChild(el);
      if (logTitle) logTitle.textContent = `${name} — stopped`;
    } catch (e) {
      if (logDiv) logDiv.innerHTML = `<div class="proj-log-line err">${esc(String(e))}</div>`;
    }
    setTimeout(() => this._loadProjects(), 1500);
  }

  _projectCloseLog() {
    if (this._projectLogCtrl) {
      this._projectLogCtrl.abort();
      this._projectLogCtrl = null;
    }
    const logWrap = $('project-log-wrap');
    if (logWrap) logWrap.style.display = 'none';
    const logDiv = $('project-log');
    if (logDiv) logDiv.innerHTML = '';
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
    const isUp   = c.status?.startsWith('Up');
    const cls    = isUp ? 'running' : 'stopped';
    const cpu    = c.cpu    || '—';
    const mem    = c.memory || '—';
    const memPct = c.mem_pct || '';
    const memVal = memPct || (mem.split('/')[0]?.trim()) || '—';
    const name   = esc(c.name);
    const n      = c.name;

    const parsePct = s => { const m = String(s).match(/(\d+\.?\d*)/); return m ? Math.min(100, parseFloat(m[1])) : 0; };
    const barClr   = v  => v > 80 ? '#f85149' : v > 50 ? '#d29922' : '#3fb950';
    const cpuPct   = parsePct(cpu);
    const memPctN  = parsePct(memVal);

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
        <div class="c-chip">
          <div class="c-chip-val">${esc(cpu)}</div>
          <div class="c-bar-wrap"><div class="c-bar-fill" style="width:${cpuPct.toFixed(1)}%;background:${barClr(cpuPct)}"></div></div>
          <div class="c-chip-lbl">CPU</div>
        </div>
        <div class="c-chip">
          <div class="c-chip-val">${esc(memVal)}</div>
          <div class="c-bar-wrap"><div class="c-bar-fill" style="width:${memPctN.toFixed(1)}%;background:${barClr(memPctN)}"></div></div>
          <div class="c-chip-lbl">Mem%</div>
        </div>
        <div class="c-chip"><div class="c-chip-val" style="font-size:10px">${esc(mem.split('/')[0]?.trim()||'—')}</div><div class="c-chip-lbl">Mem Used</div></div>
      </div>` : ''}
      <div class="c-actions">
        <button class="c-btn start"         ${isUp  ? 'disabled' : ''} onclick="window._dash._containerAction('${agentId}','${esc(n)}','start')">Start</button>
        <button class="c-btn stop"          ${!isUp ? 'disabled' : ''} onclick="window._dash._containerAction('${agentId}','${esc(n)}','stop')">Stop</button>
        <button class="c-btn restart"                                   onclick="window._dash._containerAction('${agentId}','${esc(n)}','restart')">Restart</button>
        <button class="c-btn clean-restart" title="Recreate from compose — applies volume mounts, image rebuilds, and config changes"
                onclick="window._dash._containerAction('${agentId}','${esc(n)}','clean-restart')">↺ Rebuild</button>
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

    // Global click sound — fires on every interactive element click
    const CLICK_SEL = 'button,a,.tab,.vbtn,.sidebar-item,.mem-item,.git-file-row,.change-bar-hdr,.svc-row,.agent-card,.sub-agent-card,.cc-entry,.today-item,select,input[type=checkbox],input[type=range]';
    document.addEventListener('click', e => {
      if (e.target.closest(CLICK_SEL)) this.sound.click();
    }, true);
  }
}

// Boot
document.addEventListener('DOMContentLoaded', () => {
  const dash = new Dashboard();
  dash.init();
});
