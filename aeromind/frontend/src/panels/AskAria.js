/**
 * AskAria.js — ARIA Live Race Commentator Panel
 * Fixes:
 *  - audio/L16 PCM → WAV conversion (L16 is big-endian, WAV needs little-endian + header)
 *  - Browser autoplay unlock via single user-click on ENABLE AUDIO button
 *  - AudioContext-based playback (reliable across browsers)
 */

import { gsap } from 'gsap';

// ---------------------------------------------------------------------------
// PCM L16 (big-endian, 16-bit, mono) → WAV (little-endian) converter
// ---------------------------------------------------------------------------
function pcmL16ToWav(pcmBytes, sampleRate) {
    // L16 is big-endian 16-bit signed PCM.
    // WAV needs little-endian. Byte-swap every 2-byte sample.
    const numSamples  = pcmBytes.length / 2;
    const wavData     = new Uint8Array(44 + pcmBytes.length);
    const view        = new DataView(wavData.buffer);
    const writeStr    = (off, s) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };

    const byteRate    = sampleRate * 2;       // 1 channel * 2 bytes/sample
    const dataSize    = numSamples * 2;

    // RIFF header
    writeStr(0,  'RIFF');
    view.setUint32(4,  36 + dataSize, true);
    writeStr(8,  'WAVE');
    // fmt chunk
    writeStr(12, 'fmt ');
    view.setUint32(16, 16, true);             // chunk size
    view.setUint16(20,  1, true);             // PCM
    view.setUint16(22,  1, true);             // mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, byteRate,   true);
    view.setUint16(32,  2, true);             // block align
    view.setUint16(34, 16, true);             // bits per sample
    // data chunk
    writeStr(36, 'data');
    view.setUint32(40, dataSize, true);

    // Gemini TTS returns little-endian PCM despite the audio/L16 label
    // WAV also needs little-endian — copy bytes directly, no swap needed
    for (let i = 0; i < numSamples; i++) {
        wavData[44 + i * 2]     = pcmBytes[i * 2];
        wavData[44 + i * 2 + 1] = pcmBytes[i * 2 + 1];
    }
    return wavData;
}

function parseSampleRate(mimeType) {
    // e.g. "audio/L16;codec=pcm;rate=24000"  or  "audio/pcm;rate=16000"
    const m = /rate=(\d+)/i.exec(mimeType || '');
    return m ? parseInt(m[1]) : 24000;
}

// ---------------------------------------------------------------------------
// AriaPanel
// ---------------------------------------------------------------------------
class AriaPanel {
    constructor() {
        this.feedWs        = null;
        this.isFeedLive    = false;
        this.feedEl        = null;
        this.statusEl      = null;
        this._entryCount   = 0;
        this._reconnTimer  = null;

        // Audio (TTS playback)
        this._audioCtx     = null;
        this._audioUnlocked = false;
        this._audioQueue   = [];
        this._audioPlaying = false;

        // Live Voice
        this._voiceWs      = null;
        this._voiceActive  = false;
        this._micStream    = null;
        this._micProcessor = null;
        this._micSource    = null;
    }

    // =======================================================================
    // AUDIO UNLOCK — must be triggered by user gesture
    // =======================================================================

    _unlockAudio() {
        if (this._audioUnlocked) return;
        try {
            this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            // Play silent buffer to fully unlock
            const buf = this._audioCtx.createBuffer(1, 1, 22050);
            const src = this._audioCtx.createBufferSource();
            src.buffer = buf;
            src.connect(this._audioCtx.destination);
            src.start(0);
            this._audioUnlocked = true;

            // Update button
            const btn = document.getElementById('aria-audio-btn');
            if (btn) {
                btn.textContent = '🔊 AUDIO ON';
                btn.style.color = 'var(--live-green)';
                btn.style.borderColor = 'var(--live-green)';
            }
            // Drain any queued audio immediately
            if (!this._audioPlaying) this._playNext();
        } catch (e) {
            console.warn('AudioContext init failed:', e);
        }
    }

    // =======================================================================
    // TTS AUDIO PLAYBACK  (AudioContext-based, bypasses autoplay policy)
    // =======================================================================

    _enqueueAudio(b64, mimeType) {
        this._audioQueue.push({ b64, mimeType: mimeType || 'audio/L16;rate=24000' });
        if (!this._audioPlaying && this._audioUnlocked) this._playNext();
    }

    async _playNext() {
        if (this._audioQueue.length === 0) {
            this._audioPlaying = false;
            this._setWave(false);
            return;
        }
        if (!this._audioUnlocked || !this._audioCtx) {
            this._audioPlaying = false;
            return;  // wait for user to unlock
        }

        this._audioPlaying = true;
        this._setWave(true);

        const { b64, mimeType } = this._audioQueue.shift();

        try {
            const rawBytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));

            let wavBytes;
            if (mimeType.includes('L16') || mimeType.includes('pcm')) {
                // Raw PCM — add WAV header + byte-swap
                const sr = parseSampleRate(mimeType);
                wavBytes = pcmL16ToWav(rawBytes, sr);
            } else {
                // Already WAV/MP3/OGG — use as-is
                wavBytes = rawBytes;
            }

            // Decode via AudioContext (handles WAV natively)
            const arrayBuf = wavBytes.buffer.slice(wavBytes.byteOffset, wavBytes.byteOffset + wavBytes.byteLength);
            const audioBuf = await this._audioCtx.decodeAudioData(arrayBuf);

            const src = this._audioCtx.createBufferSource();
            src.buffer = audioBuf;
            src.connect(this._audioCtx.destination);
            src.onended = () => this._playNext();
            src.start(0);

        } catch (e) {
            console.warn('ARIA audio decode error:', e);
            this._playNext();
        }
    }

    // =======================================================================
    // WEBSOCKET FEED
    // =======================================================================

    connectFeed() {
        if (this.feedWs?.readyState === WebSocket.OPEN) return;
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.feedWs = new WebSocket(`${proto}//${location.host}/aria`);

        this.feedWs.onopen = () => {
            this.isFeedLive = true;
            this._setStatus('ARIA LIVE', true);
            clearTimeout(this._reconnTimer);
            // Re-register audio opt-in if user had already unlocked
            if (this._audioUnlocked) {
                this.feedWs.send(JSON.stringify({ type: 'audio_enable' }));
            }
        };
        this.feedWs.onmessage = (e) => {
            if (typeof e.data !== 'string') return;
            try { this._onFeedMessage(JSON.parse(e.data)); } catch {}
        };
        this.feedWs.onclose = () => {
            this.isFeedLive = false;
            this._setStatus('OFFLINE', false);
            this._reconnTimer = setTimeout(() => this.connectFeed(), 5000);
        };
        this.feedWs.onerror = () => this._setStatus('ERROR', false);
    }

    _onFeedMessage(msg) {
        switch (msg.type) {
            case 'ping': break;
            case 'status':
                this._addEntry('system', msg.text);
                break;
            case 'commentary':
                this._addEntry('commentary', msg.text);
                if (msg.audio_b64) this._enqueueAudio(msg.audio_b64, msg.mime_type);
                break;
            case 'audio_update':
                if (msg.audio_b64) this._enqueueAudio(msg.audio_b64, msg.mime_type);
                break;
            case 'typing':
                this._showTyping();
                break;
            case 'answer':
                this._removeTyping();
                this._addEntry('answer', msg.text);
                break;
        }
    }

    // =======================================================================
    // UI HELPERS
    // =======================================================================

    _addEntry(role, text) {
        if (!this.feedEl) return;
        this._removeTyping();

        const el  = document.createElement('div');
        const now = new Date().toLocaleTimeString('en-GB', {
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });

        if (role === 'commentary') {
            this._entryCount++;
            el.className = 'aria-entry commentary';
            el.innerHTML = `
                <div class="aria-meta">
                    <span class="aria-meta-tag" style="color:var(--f1-orange);">
                        ⚡ ARIA &middot; EVENT #${this._entryCount}
                    </span>
                    <span class="aria-meta-time">${now}</span>
                </div>
                <div>${this._esc(text)}</div>
            `;
        } else if (role === 'answer') {
            el.className = 'aria-entry answer';
            el.innerHTML = `
                <div class="aria-meta">
                    <span class="aria-meta-tag" style="color:var(--live-green);">ARIA RESPONSE</span>
                    <span class="aria-meta-time">${now}</span>
                </div>
                <div>${this._esc(text)}</div>
            `;
        } else if (role === 'vision') {
            this._entryCount++;
            el.className = 'aria-entry commentary';
            el.innerHTML = `
                <div class="aria-meta">
                    <span class="aria-meta-tag" style="color:#a855f7;">
                        👁 ARIA VISION &middot; MULTIMODAL #${this._entryCount}
                    </span>
                    <span class="aria-meta-time">${now}</span>
                </div>
                <div>${this._esc(text)}</div>
            `;
        } else {
            el.className = 'aria-entry system';
            el.textContent = text;
        }

        this.feedEl.appendChild(el);
        gsap.to(this.feedEl, { scrollTop: this.feedEl.scrollHeight, duration: 0.4, ease: 'power2.out' });
    }

    _showTyping() {
        if (!this.feedEl || document.getElementById('aria-typing')) return;
        const el = document.createElement('div');
        el.id = 'aria-typing';
        el.className = 'aria-entry system';
        el.textContent = 'ARIA ANALYSING...';
        this.feedEl.appendChild(el);
        this.feedEl.scrollTop = this.feedEl.scrollHeight;
    }

    _removeTyping() { document.getElementById('aria-typing')?.remove(); }

    _setStatus(text, live) {
        if (!this.statusEl) return;
        this.statusEl.textContent = text;
        this.statusEl.className   = `badge ${live ? 'badge-live' : 'badge-off'}`;
    }

    _setWave(active) {
        const waveEl = document.getElementById('aria-wave');
        if (!waveEl) return;
        gsap.to(waveEl, { opacity: active ? 1 : 0.15, duration: 0.4, ease: 'power2.inOut' });
        if (active) {
            gsap.to('#aria-wave .wave-bar', {
                scaleY: () => 0.4 + Math.random() * 1.6,
                duration: 0.2,
                stagger: 0.02,
                repeat: -1,
                yoyo: true,
                ease: 'power1.inOut',
            });
        } else {
            gsap.killTweensOf('#aria-wave .wave-bar');
            gsap.to('#aria-wave .wave-bar', { scaleY: 1, duration: 0.3 });
        }
    }

    _esc(s) {
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    // =======================================================================
    // LIVE VOICE  (Gemini Live API bidirectional)
    // =======================================================================

    async _toggleVoice() {
        if (this._voiceActive) { this._stopVoice(); return; }

        // Ensure AudioContext is unlocked for playback
        if (!this._audioUnlocked) this._unlockAudio();

        try {
            this._micStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
        } catch (e) {
            this._addEntry('system', `🎙 Mic access denied: ${e.message}`);
            return;
        }

        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        this._voiceWs = new WebSocket(`${proto}//${location.host}/aria/voice`);
        this._voiceWs.binaryType = 'arraybuffer';

        this._voiceWs.onopen = () => {
            this._voiceActive = true;
            this._setVoiceBtn(true);
            // Capture raw PCM 16kHz via ScriptProcessor → send to server
            const micCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
            this._micSource    = micCtx.createMediaStreamSource(this._micStream);
            this._micProcessor = micCtx.createScriptProcessor(4096, 1, 1);
            this._micProcessor.onaudioprocess = (ev) => {
                if (this._voiceWs?.readyState !== WebSocket.OPEN) return;
                const f32 = ev.inputBuffer.getChannelData(0);
                const i16 = new Int16Array(f32.length);
                for (let i = 0; i < f32.length; i++)
                    i16[i] = Math.max(-32768, Math.min(32767, f32[i] * 32768));
                this._voiceWs.send(i16.buffer);
            };
            this._micSource.connect(this._micProcessor);
            this._micProcessor.connect(micCtx.destination);
        };

        this._voiceWs.onmessage = (e) => {
            if (typeof e.data !== 'string') return;
            try {
                const msg = JSON.parse(e.data);
                if (msg.type === 'voice_ready') {
                    this._addEntry('system', '🎙 ' + msg.text);
                } else if (msg.type === 'aria_audio') {
                    this._enqueueAudio(msg.data, msg.mime_type || 'audio/pcm;rate=24000');
                } else if (msg.type === 'voice_error') {
                    this._addEntry('system', `⚠ Voice: ${msg.text}`);
                    this._stopVoice();
                }
            } catch {}
        };

        this._voiceWs.onclose = () => this._stopVoice();
        this._voiceWs.onerror = () => {
            this._addEntry('system', '⚠ Voice connection failed');
            this._stopVoice();
        };
    }

    _stopVoice() {
        this._voiceActive = false;
        this._setVoiceBtn(false);
        this._micProcessor?.disconnect();
        this._micSource?.disconnect();
        this._micStream?.getTracks().forEach(t => t.stop());
        this._voiceWs?.close();
        this._voiceWs      = null;
        this._micStream    = null;
        this._micProcessor = null;
        this._micSource    = null;
    }

    _setVoiceBtn(active) {
        const btn = document.getElementById('aria-voice-btn');
        if (!btn) return;
        if (active) {
            btn.textContent = '🔴 END VOICE';
            btn.style.color = 'var(--f1-orange)';
            btn.style.borderColor = 'var(--f1-orange)';
        } else {
            btn.textContent = '🎙 LIVE VOICE';
            btn.style.color = 'var(--live-green)';
            btn.style.borderColor = 'var(--live-green)';
        }
    }

    // =======================================================================
    // RENDER
    // =======================================================================

    render(containerId) {
        document.getElementById(containerId).innerHTML = `
            <div class="f1-panel" style="height:100%;">

                <div class="f1-panel-header">
                    <span class="f1-panel-title">ARIA — AI Race Commentator</span>
                    <div style="display:flex;gap:6px;align-items:center;">
                        <button id="aria-audio-btn" style="
                            background:none;
                            border:1px solid var(--f1-orange);
                            color:var(--f1-orange);
                            font-family:var(--font-hud);
                            font-size:.5rem;
                            letter-spacing:1px;
                            padding:4px 10px;
                            cursor:pointer;
                            border-radius:2px;
                            transition:all 0.2s;
                        ">🔇 ENABLE AUDIO</button>
                        <span id="aria-status" class="badge badge-off">OFFLINE</span>
                    </div>
                </div>

                <!-- Waveform — animates when ARIA is speaking -->
                <div id="aria-wave" style="
                    height:28px;
                    background:rgba(255,128,0,0.05);
                    padding:0 14px; flex-shrink:0;
                    display:flex; align-items:center; gap:2px;
                    opacity:0.15;
                ">
                    ${Array.from({length: 36}, (_, i) =>
                        `<div class="wave-bar" style="
                            width:3px;
                            height:${5 + Math.abs(Math.sin(i * 0.55)) * 14}px;
                            background:var(--f1-orange);
                            border-radius:1px;
                            transform-origin:center;
                        "></div>`
                    ).join('')}
                </div>

                <!-- Commentary feed -->
                <div class="f1-panel-body" id="aria-feed">
                    <div class="aria-entry system">
                        ARIA online — click ENABLE AUDIO then wait for race events&hellip;
                    </div>
                </div>

                <div style="
                    padding:5px 14px;
                    border-top:1px solid var(--f1-border);
                    flex-shrink:0;
                    font-family:var(--font-hud);
                    font-size:.48rem;
                    color:rgba(255,255,255,.18);
                    letter-spacing:1px;
                    text-align:center;
                ">
                    Gemini TTS &middot; Vertex AI &middot; ADK Pit Wall &middot; F1 2026 Regs
                </div>

            </div>
        `;

        this.statusEl = document.getElementById('aria-status');
        this.feedEl   = document.getElementById('aria-feed');

        // Wire up ENABLE AUDIO button — also tells server to start sending TTS audio
        document.getElementById('aria-audio-btn').addEventListener('click', () => {
            this._unlockAudio();
            // Notify server: this client wants TTS audio
            if (this.feedWs?.readyState === WebSocket.OPEN) {
                this.feedWs.send(JSON.stringify({ type: 'audio_enable' }));
            }
        });

        // connectFeed() is called by launchSystem() — not here.
        // This prevents the WebSocket from opening before the user clicks LAUNCH,
        // which would make the backend think someone is active and burn Gemini credits.

        // Listen for multimodal vision analysis results from F1Track
        window.addEventListener('aria-frame-analysis', (e) => {
            const { text, audio_b64, mime_type } = e.detail;
            this._addEntry('vision', text);
            if (audio_b64) this._enqueueAudio(audio_b64, mime_type);
        });
    }
}

export default AriaPanel;
