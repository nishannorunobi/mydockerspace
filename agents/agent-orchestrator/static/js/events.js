/**
 * EventStream — single SSE connection for all real-time events:
 *   alerts, status changes, workspace file changes.
 * Dispatches to registered handlers by event type.
 */
class EventStream {
  constructor() {
    this._handlers = {};
    this._es       = null;
  }

  on(type, fn) {
    if (!this._handlers[type]) this._handlers[type] = [];
    this._handlers[type].push(fn);
  }

  connect() {
    if (this._es) { this._es.close(); }
    this._es = new EventSource('/api/events/stream');

    this._es.onopen = () => this._emit('_connected');

    this._es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        this._emit(data.type, data);
        // also emit generic 'any' for debugging
        this._emit('any', data);
      } catch {}
    };

    this._es.onerror = () => {
      this._emit('_disconnected');
      this._es.close();
      setTimeout(() => this.connect(), 5000);
    };
  }

  _emit(type, data) {
    (this._handlers[type] || []).forEach(fn => fn(data));
  }
}

window.EventStream = EventStream;
