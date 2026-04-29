/**
 * SoundSystem — generates alert tones via Web Audio API.
 * No audio files needed; all tones are synthesised programmatically.
 */
class SoundSystem {
  constructor() {
    this._nodes = [];   // track active nodes so we can stop them
    this.__ctx  = null;
  }

  _ctx() {
    if (!this.__ctx) this.__ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (this.__ctx.state === 'suspended') this.__ctx.resume();
    return this.__ctx;
  }

  /** Stop any currently playing alert sound. */
  stop() {
    this._nodes.forEach(n => { try { n.stop(0); } catch {} });
    this._nodes = [];
  }

  /**
   * Play a sound type.
   * @param {'alarm'|'warning'|'info'|'none'} type
   * @param {number} volume  0–1
   * @param {number} duration  seconds
   */
  play(type, volume = 0.7, duration = 10) {
    this.stop();
    const ctx = this._ctx();
    switch (type) {
      case 'alarm':   this._alarm(ctx, volume, duration);   break;
      case 'warning': this._warning(ctx, volume, duration); break;
      case 'info':    this._info(ctx, volume);              break;
      case 'none':    break;
    }
  }

  /* ── Alarm: rapid alternating hi/lo beeps ── */
  _alarm(ctx, vol, dur) {
    const count = Math.ceil(dur / 0.5);
    for (let i = 0; i < count; i++) {
      this._beep(ctx, i % 2 === 0 ? 880 : 440, ctx.currentTime + i * 0.5, 0.45, vol);
    }
  }

  /* ── Warning: medium repeating beeps ── */
  _warning(ctx, vol, dur) {
    const count = Math.max(1, Math.floor(dur / 0.9));
    for (let i = 0; i < count; i++) {
      this._beep(ctx, 660, ctx.currentTime + i * 0.9, 0.35, vol);
    }
  }

  /* ── Info: single short chime ── */
  _info(ctx, vol) {
    this._beep(ctx, 523, ctx.currentTime, 0.3, vol * 0.6);
    this._beep(ctx, 659, ctx.currentTime + 0.15, 0.3, vol * 0.5);
  }

  _beep(ctx, freq, start, len, vol) {
    const osc  = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'square';
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(vol * 0.3, start);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + len);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start(start);
    osc.stop(start + len + 0.01);
    this._nodes.push(osc);
  }
}

window.SoundSystem = SoundSystem;
