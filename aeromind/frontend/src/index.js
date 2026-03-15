/**
 * AeroMind 2026 — Main Orchestrator
 * Three.js atmospheric background + F1Track + TelemetryPanel + AriaPanel + ChroniclePanel
 */

import * as THREE from 'three';
import { gsap } from 'gsap';
import { F1Track }        from './track/F1Track.js';
import { TelemetryPanel } from './panels/TelemetryPanel.js';
import { ChroniclePanel } from './panels/ChroniclePanel.js';
import AriaPanel          from './panels/AskAria.js';
import { GraphPanel }     from './panels/GraphPanel.js';

// ============================================================
// THREE.JS ATMOSPHERIC BACKGROUND
// ============================================================
function initBackground() {
    const canvas = document.getElementById('bg-canvas');
    if (!canvas) return;

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(window.innerWidth, window.innerHeight);

    const scene  = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.z = 5;

    // Particle field — floating data points like timing screens
    const PARTICLE_COUNT = 800;
    const positions = new Float32Array(PARTICLE_COUNT * 3);
    const colors    = new Float32Array(PARTICLE_COUNT * 3);

    // F1 color palette for particles
    const palette = [
        new THREE.Color('#E10600'),  // F1 red
        new THREE.Color('#3671C6'),  // Red Bull blue
        new THREE.Color('#27F4D2'),  // Mercedes teal
        new THREE.Color('#FF8000'),  // McLaren orange
        new THREE.Color('#E8002D'),  // Ferrari red
        new THREE.Color('#ffffff'),  // white
    ];

    for (let i = 0; i < PARTICLE_COUNT; i++) {
        positions[i * 3]     = (Math.random() - 0.5) * 20;
        positions[i * 3 + 1] = (Math.random() - 0.5) * 12;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 8;

        const col = palette[Math.floor(Math.random() * palette.length)];
        colors[i * 3]     = col.r;
        colors[i * 3 + 1] = col.g;
        colors[i * 3 + 2] = col.b;
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('color',    new THREE.BufferAttribute(colors, 3));

    const mat = new THREE.PointsMaterial({
        size:         0.04,
        vertexColors: true,
        transparent:  true,
        opacity:      0.6,
        sizeAttenuation: true,
    });

    const points = new THREE.Points(geo, mat);
    scene.add(points);

    // Speed lines — horizontal streaks for motion feel
    const lineGeo = new THREE.BufferGeometry();
    const lineCount = 30;
    const linePos   = new Float32Array(lineCount * 6);

    for (let i = 0; i < lineCount; i++) {
        const y = (Math.random() - 0.5) * 12;
        const z = (Math.random() - 0.5) * 4;
        const x0 = (Math.random() - 0.5) * 20;
        const len = 0.3 + Math.random() * 1.2;
        linePos[i * 6]     = x0;       linePos[i * 6 + 1] = y; linePos[i * 6 + 2] = z;
        linePos[i * 6 + 3] = x0 + len; linePos[i * 6 + 4] = y; linePos[i * 6 + 5] = z;
    }

    lineGeo.setAttribute('position', new THREE.BufferAttribute(linePos, 3));
    const lineMat = new THREE.LineBasicMaterial({ color: '#E10600', transparent: true, opacity: 0.15 });
    const lines   = new THREE.LineSegments(lineGeo, lineMat);
    scene.add(lines);

    // Animate
    let frame = 0;
    function animate() {
        requestAnimationFrame(animate);
        frame++;

        // Slow drift
        points.rotation.y += 0.0003;
        points.rotation.x += 0.0001;

        // Subtle camera parallax
        camera.position.x = Math.sin(frame * 0.0005) * 0.3;
        camera.position.y = Math.cos(frame * 0.0003) * 0.2;

        // Speed line motion
        const pos = lineGeo.attributes.position.array;
        for (let i = 0; i < lineCount; i++) {
            pos[i * 6]     -= 0.05;
            pos[i * 6 + 3] -= 0.05;
            if (pos[i * 6 + 3] < -10) {
                const reset = 10 + Math.random() * 2;
                pos[i * 6]     = reset;
                pos[i * 6 + 3] = reset + 0.3 + Math.random() * 1.2;
            }
        }
        lineGeo.attributes.position.needsUpdate = true;

        renderer.render(scene, camera);
    }
    animate();

    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });
}

// ============================================================
// LIVE CLOCK
// ============================================================
function startClock() {
    const el = document.getElementById('clock');
    if (!el) return;
    function tick() {
        el.textContent = new Date().toLocaleTimeString('en-GB', {
            hour:   '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
    }
    tick();
    setInterval(tick, 1000);
}

// ============================================================
// SPLASH SCREEN — animated racing cars + system status checks
// ============================================================
function initSplash() {
    const splash    = document.getElementById('splash');
    const splashMsg = document.getElementById('splash-msg');
    if (!splash) return;

    // Animate cars around the oval splash track
    const pathEl = document.getElementById('splash-path');
    if (!pathEl) return;
    const total  = pathEl.getTotalLength();

    // offsets along the path (0–1) for 4 cars
    const offsets = [0, 0.27, 0.54, 0.78];
    const carIds  = ['sc1', 'sc2', 'sc3', 'sc4'];
    const progresses = offsets.map(o => ({ t: o }));

    function positionCar(carId, t) {
        const el = document.getElementById(carId);
        if (!el) return;
        const dist = ((t % 1) + 1) % 1;
        const pt   = pathEl.getPointAtLength(dist * total);
        el.setAttribute('transform', `translate(${pt.x},${pt.y})`);
    }

    // Start each car at its offset
    offsets.forEach((_, i) => positionCar(carIds[i], offsets[i]));

    // Racing animation — different speeds for overtake drama
    const speeds = [0.0008, 0.00075, 0.00085, 0.00070];
    let raf;
    function animateCars() {
        progresses.forEach((p, i) => {
            p.t += speeds[i];
            positionCar(carIds[i], p.t);
        });
        raf = requestAnimationFrame(animateCars);
    }
    animateCars();

    // Rotating status messages
    const msgs = [
        'AWAITING LIVE SESSION',
        'MEMGRAPH GRAPH DB READY',
        'ARIA AI COMMENTATOR ONLINE',
        'ADK PIT WALL AGENTS ARMED',
        'MONTE CARLO SIMULATIONS RUNNING',
        'RACE TELEMETRY STREAMING',
    ];
    let msgIdx = 0;
    const msgTimer = setInterval(() => {
        msgIdx = (msgIdx + 1) % msgs.length;
        if (splashMsg) splashMsg.textContent = msgs[msgIdx];
    }, 600);

    // System checks — tick off quickly
    const checks = ['sc-memgraph', 'sc-aria', 'sc-adk', 'sc-openf1'];
    checks.forEach((id, i) => {
        setTimeout(() => {
            const el = document.getElementById(id);
            if (el) {
                el.classList.add('ok');
                el.querySelector('.sc-icon').textContent = '✓';
            }
        }, 200 + i * 250);
    });

    // Expose dismiss function for when real data arrives
    splash._dismiss = () => {
        cancelAnimationFrame(raf);
        clearInterval(msgTimer);
        splash.classList.add('hidden');
    };
}

// ============================================================
// ENTRY POINT
// ============================================================
document.addEventListener('DOMContentLoaded', () => {

    // Background + clock + splash
    initBackground();
    startClock();
    initSplash();

    // Instantiate panels
    const track      = new F1Track();
    const telemetry  = new TelemetryPanel();
    const chronicle  = new ChroniclePanel();
    const aria       = new AriaPanel();
    const graph      = new GraphPanel();

    // Mount to HTML
    track.render('track-mount');
    telemetry.render('telemetry-mount');
    chronicle.render('chronicle-panel-mount');
    aria.render('aria-panel-mount');
    graph.render('graph-mount');

    // Topbar entrance animation
    gsap.from('#topbar', { y: -52, opacity: 0, duration: 0.6, ease: 'power2.out' });
    gsap.from('#telemetry-mount', { x: -40, opacity: 0, duration: 0.7, delay: 0.15, ease: 'power2.out' });
    gsap.from('#track-mount',     { y: 20, opacity: 0, duration: 0.7, delay: 0.25, ease: 'power2.out' });
    gsap.from('#graph-mount',     { y: 20, opacity: 0, duration: 0.7, delay: 0.35, ease: 'power2.out' });
    gsap.from('#aria-panel-mount',{ x: 40, opacity: 0, duration: 0.7, delay: 0.35, ease: 'power2.out' });
    gsap.from('#chronicle-bar',   { y: 96, opacity: 0, duration: 0.6, delay: 0.5, ease: 'power2.out' });

    // ── Tab visibility ────────────────────────────────────────
    let tabVisible = !document.hidden;
    document.addEventListener('visibilitychange', () => {
        tabVisible = !document.hidden;
    });

    // ── System activation gate ────────────────────────────────
    // Nothing runs until the user clicks LAUNCH RACE INTELLIGENCE.
    // This prevents any backend calls (and Gemini spend) until explicitly started.
    let systemActive = false;

    async function launchSystem() {
        if (systemActive) return;
        systemActive = true;

        // Read selected session from splash dropdown and apply it
        const splashSelect = document.getElementById('splash-race-select');
        const selectedKey  = splashSelect?.value || 'demo';

        // Sync the topbar dropdown to match
        const topbarSelect = document.getElementById('race-select');
        if (topbarSelect) topbarSelect.value = selectedKey;

        // Animate button → loading state
        const btn = document.getElementById('launch-btn');
        if (btn) {
            btn.textContent  = '⏳  INITIALISING...';
            btn.style.animation = 'none';
            btn.style.background = 'rgba(225,6,0,0.3)';
            btn.disabled = true;
        }
        if (splashSelect) splashSelect.disabled = true;

        // Apply the selected session to the backend
        try {
            await fetch('/api/session', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ session_key: selectedKey }),
            });
        } catch {}

        // Send heartbeat immediately — activates Gemini on backend
        sendHeartbeat();

        // Mark button done
        if (btn) {
            btn.textContent  = '✓  SYSTEMS ONLINE';
            btn.style.background = 'linear-gradient(135deg,#00a86b,#007a4d)';
            btn.style.boxShadow  = '0 0 30px rgba(0,168,107,0.5)';
        }

        // Connect ARIA WebSocket feed (deferred until now)
        aria.connectFeed();

        // Start all polling
        pollSnapshot();
        pollChronicle();
        setInterval(pollSnapshot,  2000);
        setInterval(pollChronicle, 3000);
        setInterval(sendHeartbeat, 20000);
    }

    // Wire the splash LAUNCH button
    document.getElementById('launch-btn')?.addEventListener('click', launchSystem);

    // ── Heartbeat ─────────────────────────────────────────────
    async function sendHeartbeat() {
        if (!tabVisible || !systemActive) return;
        try { await fetch('/api/heartbeat', { method: 'POST' }); } catch {}
    }

    // ── Snapshot polling: track + telemetry ──────────────────
    let lastSnapshotTime = 0;

    let splashDismissed = false;

    async function pollSnapshot() {
        if (!tabVisible) return;
        try {
            const res = await fetch('/api/snapshot');
            if (!res.ok) return;
            const snap = await res.json();

            // Dismiss splash on first real data
            if (!splashDismissed && snap.cars?.length > 0) {
                splashDismissed = true;
                const sp = document.getElementById('splash');
                if (sp?._dismiss) sp._dismiss();
            }

            // Debounce: only update if data changed meaningfully
            const t = Date.now();
            if (t - lastSnapshotTime > 1800) {
                lastSnapshotTime = t;
                track.update(snap);
                telemetry.update(snap);

                // Update session label car count
                const countEl = document.getElementById('session-label');
                if (countEl && snap.cars?.length) {
                    countEl.textContent = `${snap.cars.length} CARS · RACE`;
                }
            }
        } catch (err) {
            // Silent — backend may still be starting
        }
    }

    // ── Chronicle polling ─────────────────────────────────────
    const seenIds = new Set();

    async function pollChronicle() {
        if (!tabVisible) return;
        try {
            const res = await fetch('/api/chronicle');
            if (!res.ok) return;
            const data = await res.json();
            (data.entries || []).forEach(entry => {
                if (!seenIds.has(entry.id)) {
                    seenIds.add(entry.id);
                    chronicle.addEntry(entry.text, entry.id, entry.imageUrl);
                }
            });
        } catch {}
    }

    // ── Graph polling ─────────────────────────────────────────
    async function pollGraph() {
        if (!tabVisible) return;
        try {
            const res = await fetch('/api/graph');
            if (!res.ok) return;
            const data = await res.json();
            graph.update(data);
        } catch {}
    }
    pollGraph();
    setInterval(pollGraph, 2500);

    // Graph polling starts immediately (no Gemini cost — just reads Memgraph)

    // ── OpenF1 lock banner — full-screen centered overlay ─────
    function setLockBanner(msg) {
        let el = document.getElementById('openf1-lock-banner');
        if (msg) {
            if (!el) {
                el = document.createElement('div');
                el.id = 'openf1-lock-banner';
                el.innerHTML = `
                    <div style="
                        background:rgba(8,4,0,0.97);
                        border:2px solid var(--f1-orange);
                        border-radius:6px;
                        padding:36px 48px;
                        max-width:580px;
                        text-align:center;
                        box-shadow:0 0 60px rgba(255,128,0,0.25), 0 0 120px rgba(255,128,0,0.08);
                        position:relative;
                    ">
                        <button id="lock-banner-close" style="
                            position:absolute;top:12px;right:16px;
                            background:none;border:none;cursor:pointer;
                            font-family:var(--font-hud);font-size:.7rem;
                            color:rgba(255,128,0,.4);letter-spacing:1px;
                        " title="Dismiss">✕</button>
                        <div style="
                            font-family:var(--font-hud);font-size:1.8rem;
                            font-weight:900;color:var(--f1-orange);
                            letter-spacing:4px;margin-bottom:8px;
                            text-shadow:0 0 20px rgba(255,128,0,0.5);
                        ">⚑ LIVE RACE IN PROGRESS</div>
                        <div style="
                            width:60px;height:2px;
                            background:var(--f1-orange);
                            margin:0 auto 20px;
                            opacity:.6;
                        "></div>
                        <div id="lock-banner-msg" style="
                            font-family:var(--font-hud);font-size:.65rem;
                            color:rgba(255,200,100,.85);letter-spacing:1.5px;
                            line-height:1.9;margin-bottom:20px;
                        "></div>
                        <div style="
                            display:flex;gap:20px;justify-content:center;
                            font-family:var(--font-hud);font-size:.5rem;
                            color:rgba(255,255,255,.25);letter-spacing:1px;
                        ">
                            <span>● MEMGRAPH LIVE</span>
                            <span>● 2026 SIMULATION RUNNING</span>
                            <span>● AI MONITORING</span>
                        </div>
                    </div>
                `;
                el.style.cssText = `
                    position:fixed;inset:0;
                    z-index:9998;
                    display:flex;align-items:center;justify-content:center;
                    background:rgba(0,0,0,0.65);
                    backdrop-filter:blur(4px);
                    -webkit-backdrop-filter:blur(4px);
                    animation:fadeIn .4s ease;
                `;
                document.body.appendChild(el);
                document.getElementById('lock-banner-close')
                    ?.addEventListener('click', () => el.remove());
            }
            const msgEl = document.getElementById('lock-banner-msg');
            if (msgEl) msgEl.textContent = msg;
        } else if (el) {
            el.remove();
        }
    }

    // ── Health + session indicator ────────────────────────────
    async function checkHealth() {
        try {
            const [hRes, sRes] = await Promise.all([
                fetch('/api/health'),
                fetch('/api/session-info'),
            ]);

            if (hRes.ok) {
                const h = await hRes.json();
                const badge = document.getElementById('live-badge');
                if (badge) {
                    if (h.openf1_locked) {
                        badge.textContent = '● LOCKED';
                        badge.style.color = 'var(--f1-orange)';
                    } else if (h.memgraph_connected) {
                        badge.textContent = '● LIVE';
                        badge.style.color = 'var(--live-green)';
                    } else {
                        badge.textContent = '● NO DATA';
                        badge.style.color = 'var(--f1-orange)';
                    }
                }
                // Show/hide the lock banner
                setLockBanner(h.openf1_locked ? h.openf1_lock_msg : '');
            }

            if (sRes.ok) {
                const s = await sRes.json();
                const lbl = document.getElementById('session-label');
                if (lbl) {
                    if (s.demo_mode) {
                        lbl.textContent = `DEMO · ${s.car_count} CARS · F1 2026`;
                    } else {
                        lbl.textContent = `SESSION ${s.resolved_key} · ${s.car_count} CARS · LIVE`;
                    }
                }
            }
        } catch {}
    }
    checkHealth();
    setInterval(checkHealth, 10000);

    // ── Race selector dropdown ──────────────────────────────────
    const raceSelect = document.getElementById('race-select');
    const sessionBtn = document.getElementById('session-btn');

    async function loadSession(key) {
        sessionBtn.textContent = '...';
        sessionBtn.disabled = true;
        try {
            const res = await fetch('/api/session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_key: key }),
            });
            const data = await res.json();
            if (data.status === 'ok') {
                seenIds.clear();
                splashDismissed = false;
                const lbl = document.getElementById('session-label');
                const opt = raceSelect?.options[raceSelect.selectedIndex];
                if (lbl) lbl.textContent = opt ? opt.text.replace('🏎 ', '') : `SESSION ${key}`;
                sessionBtn.textContent = '✓';
            } else {
                sessionBtn.textContent = 'ERR';
            }
        } catch {
            sessionBtn.textContent = 'ERR';
        }
        setTimeout(() => { sessionBtn.textContent = 'LOAD'; sessionBtn.disabled = false; }, 2000);
    }

    if (sessionBtn) {
        sessionBtn.addEventListener('click', () => {
            const key = raceSelect?.value || 'demo';
            loadSession(key);
        });
    }
});
