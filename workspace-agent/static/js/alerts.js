/**
 * AlertSystem — handles incoming alert events:
 *   - Plays configurable sounds via SoundSystem
 *   - Changes browser tab title + favicon colour
 *   - Shows/dismisses banner in the UI
 *   - Maintains alert history in the sidebar
 */
class AlertSystem {
  constructor(sound) {
    this._sound    = sound;
    this._settings = this._defaults();
    this._active   = null;   // currently displayed banner
    this._history  = [];     // [{alert, ts}]
    this._stopTimer = null;

    this._origTitle  = document.title;
    this._origFavicon = this._getFaviconHref();
  }

  // ── Settings ──────────────────────────────────────────────────────────────

  _defaults() {
    return {
      enabled: true,
      volume: 0.7,
      rules: {
        agent_down:      { enabled: true, sound: 'alarm',   duration: 10, severity: 'critical' },
        agent_recovered: { enabled: true, sound: 'info',    duration: 2,  severity: 'info'     },
        workspace_anomaly:{ enabled: true, sound: 'warning', duration: 5,  severity: 'warning'  },
      },
    };
  }

  async loadSettings() {
    try {
      const res  = await fetch('/api/alerts/settings');
      const data = await res.json();
      if (data && data.rules) this._settings = data;
    } catch {}
  }

  async saveSettings(settings) {
    this._settings = settings;
    await fetch('/api/alerts/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
  }

  getSettings() { return this._settings; }

  // ── Incoming alert ────────────────────────────────────────────────────────

  handle(alert) {
    this._history.unshift({ ...alert, receivedAt: new Date() });
    if (this._history.length > 50) this._history.pop();
    this._renderHistory();

    if (!this._settings.enabled) return;

    const rule = this._settings.rules[alert.alert_type];
    if (!rule || !rule.enabled) return;

    const sev = rule.severity || alert.severity || 'warning';
    this._showBanner(alert.message, sev, alert.agent_name);
    this._setTab(sev);
    this._playSound(rule.sound, rule.duration);
  }

  dismissAll() {
    this._hideBanner();
    this._clearTab();
    this._sound.stop();
    clearTimeout(this._stopTimer);
  }

  // ── Sound ─────────────────────────────────────────────────────────────────

  _playSound(type, duration) {
    clearTimeout(this._stopTimer);
    this._sound.play(type, this._settings.volume, duration);
    this._stopTimer = setTimeout(() => this._sound.stop(), duration * 1000);
  }

  testSound(type) {
    const dur = this._settings.rules[type]?.duration || 3;
    this._playSound(this._settings.rules[type]?.sound || type, Math.min(dur, 3));
  }

  // ── Banner ────────────────────────────────────────────────────────────────

  _showBanner(message, severity, agentName) {
    this._hideBanner();
    const container = document.getElementById('alert-container');
    const div = document.createElement('div');
    div.className = `alert-banner ${severity}`;
    const ts = new Date().toLocaleTimeString();
    div.innerHTML = `
      <span class="alert-banner-msg"><strong>[${agentName}]</strong> ${esc(message)}</span>
      <span class="alert-banner-time">${ts}</span>
      <button class="alert-dismiss" onclick="window._dash.alerts.dismissAll()">✕</button>`;
    container.appendChild(div);
    this._active = div;
  }

  _hideBanner() {
    if (this._active) { this._active.remove(); this._active = null; }
  }

  // ── Tab ───────────────────────────────────────────────────────────────────

  _setTab(severity) {
    const colours = { critical: '#f85149', warning: '#d29922', info: '#58a6ff' };
    const col = colours[severity] || colours.warning;
    const icons = { critical: '🔴', warning: '🟡', info: '🔵' };
    document.title = `${icons[severity] || '⚠'} ALERT | ${this._origTitle}`;
    this._setFavicon(col);
  }

  _clearTab() {
    document.title = this._origTitle;
    if (this._origFavicon) this._setFaviconHref(this._origFavicon);
  }

  _setFavicon(colour) {
    const c = document.createElement('canvas');
    c.width = c.height = 32;
    const ctx = c.getContext('2d');
    ctx.beginPath();
    ctx.arc(16, 16, 13, 0, Math.PI * 2);
    ctx.fillStyle = colour;
    ctx.fill();
    // pulsing ring
    ctx.beginPath();
    ctx.arc(16, 16, 13, 0, Math.PI * 2);
    ctx.strokeStyle = '#ffffff44';
    ctx.lineWidth = 2;
    ctx.stroke();
    this._setFaviconHref(c.toDataURL());
  }

  _getFaviconHref() {
    const el = document.querySelector("link[rel*='icon']");
    return el ? el.href : null;
  }

  _setFaviconHref(href) {
    let el = document.querySelector("link[rel*='icon']");
    if (!el) { el = document.createElement('link'); el.rel = 'icon'; document.head.appendChild(el); }
    el.href = href;
  }

  // ── History sidebar ───────────────────────────────────────────────────────

  _renderHistory() {
    const el = document.getElementById('alert-history');
    if (!el) return;
    if (!this._history.length) {
      el.innerHTML = '<div style="padding:8px 12px;color:var(--text3);font-size:11px">No alerts yet.</div>';
      return;
    }
    el.innerHTML = this._history.slice(0, 15).map(a => {
      const ts = a.receivedAt.toLocaleTimeString();
      return `<div class="alert-hist-item ${a.severity || 'warning'}" onclick="window._dash.alerts.dismissAll()">
        <div class="alert-hist-msg">${esc(a.message)}</div>
        <div class="alert-hist-time">${ts} · ${esc(a.agent_name)}</div>
      </div>`;
    }).join('');
  }

  getHistory() { return this._history; }
}

window.AlertSystem = AlertSystem;
