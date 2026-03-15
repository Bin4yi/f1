/**
 * F1Track.js — Live circuit visualization
 * SVG track map + GSAP animated car markers
 * Positions are computed from live Memgraph y-coordinate telemetry
 */

import { gsap } from 'gsap';

// Team color lookup — dynamic, no hardcoding
const TEAM_COLORS = {
    'Red Bull':   '#3671C6',
    'Ferrari':    '#E8002D',
    'McLaren':    '#FF8000',
    'Mercedes':   '#27F4D2',
    'Alpine':     '#FF69B4',
    'Williams':   '#64C4FF',
    'Haas':       '#B6BABD',
    'Sauber':     '#00E64D',
    'Aston Martin': '#358C75',
    'VCARB':      '#2B4562',
};

function teamColor(team) {
    return TEAM_COLORS[team] || '#AAAAAA';
}

// Generic F1 circuit path (viewBox 0 0 800 550)
// Inspired by a typical clockwise street circuit
const CIRCUIT_D = `
  M 400,50
  C 500,50 620,60 680,120
  L 740,180
  C 760,210 760,250 740,270
  L 700,310
  C 680,330 660,335 640,330
  L 580,310
  C 550,300 540,280 540,260
  C 540,240 550,220 570,210
  L 620,190
  C 640,180 650,160 640,140
  C 630,120 600,110 570,115
  L 480,130
  C 450,135 430,145 420,165
  L 400,200
  C 385,225 380,255 390,280
  L 430,340
  C 445,365 445,390 430,410
  L 390,440
  C 360,465 310,470 280,455
  L 220,430
  C 185,410 175,375 185,345
  L 200,290
  C 210,260 225,245 250,238
  L 310,225
  C 335,218 350,200 350,175
  L 345,130
  C 340,95 360,60 400,50
  Z
`;

// Precompute arc length samples for positioning cars on the path
function buildPathSampler(svgPathEl, numSamples = 500) {
    const total = svgPathEl.getTotalLength();
    const samples = [];
    for (let i = 0; i <= numSamples; i++) {
        const t = i / numSamples;
        const pt = svgPathEl.getPointAtLength(t * total);
        samples.push({ t, x: pt.x, y: pt.y, dist: t * total });
    }
    return { samples, total };
}

function getPositionOnPath(sampler, fraction) {
    const idx = Math.round(fraction * sampler.samples.length);
    const clamped = Math.max(0, Math.min(sampler.samples.length - 1, idx));
    return sampler.samples[clamped];
}

// ---------------------------------------------------------------------------
// Vision modal — full-screen overlay showing Gemini multimodal result
// ---------------------------------------------------------------------------
function _showVisionModal(state, text = '') {
    // Remove any existing modal
    document.getElementById('vision-modal')?.remove();

    const el = document.createElement('div');
    el.id = 'vision-modal';
    el.style.cssText = `
        position:fixed; inset:0; z-index:9999;
        display:flex; align-items:center; justify-content:center;
        background:rgba(5,0,20,0.82); backdrop-filter:blur(6px);
        animation:vision-fade-in .3s ease;
    `;

    if (state === 'loading') {
        el.innerHTML = `
            <div style="text-align:center; font-family:Orbitron,monospace;">
                <div style="font-size:2.5rem; margin-bottom:18px; animation:spin 1.2s linear infinite; display:inline-block;">👁</div>
                <div style="color:#a855f7; font-size:.85rem; letter-spacing:3px; font-weight:700;">ARIA VISION</div>
                <div style="color:rgba(255,255,255,.4); font-size:.6rem; letter-spacing:2px; margin-top:8px;">GEMINI MULTIMODAL ANALYSING RACE FRAME...</div>
            </div>
        `;
    } else if (state === 'result') {
        // Split into sentences for better visual layout
        const sentences = text.replace(/([.!?])\s+/g, '$1\n').split('\n').filter(Boolean);
        const sentenceHtml = sentences.map((s, i) => `
            <div style="
                padding: 10px 0;
                border-bottom: ${i < sentences.length - 1 ? '1px solid rgba(168,85,247,0.15)' : 'none'};
                font-size: ${i === 0 ? '.95rem' : '.82rem'};
                color: ${i === 0 ? '#fff' : 'rgba(255,255,255,.75)'};
                line-height:1.55;
                letter-spacing: ${i === 0 ? '.02em' : '0'};
            ">${s.trim()}</div>
        `).join('');

        el.innerHTML = `
            <div style="
                max-width:640px; width:92%;
                background:linear-gradient(145deg,rgba(20,5,40,0.98),rgba(10,0,25,0.98));
                border:1.5px solid #a855f7;
                border-radius:6px;
                box-shadow:0 0 60px rgba(168,85,247,0.35), 0 0 120px rgba(168,85,247,0.12);
                overflow:hidden;
                animation:vision-slide-in .35s cubic-bezier(.22,1,.36,1);
            ">
                <!-- Header bar -->
                <div style="
                    background:linear-gradient(90deg,#a855f7,#7c3aed);
                    padding:12px 18px;
                    display:flex; align-items:center; justify-content:space-between;
                ">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span style="font-size:1.2rem;">👁</span>
                        <div>
                            <div style="font-family:Orbitron,monospace;font-size:.75rem;font-weight:700;color:#fff;letter-spacing:2px;">ARIA VISION ANALYSIS</div>
                            <div style="font-size:.52rem;color:rgba(255,255,255,.65);letter-spacing:1px;margin-top:1px;">GEMINI 2.5 FLASH · MULTIMODAL · LIVE CIRCUIT</div>
                        </div>
                    </div>
                    <button id="vision-close" style="
                        background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.25);
                        color:#fff; width:26px; height:26px; border-radius:50%;
                        cursor:pointer; font-size:.75rem; line-height:1;
                    ">✕</button>
                </div>
                <!-- Body -->
                <div style="padding:20px 22px 16px;">
                    ${sentenceHtml}
                </div>
                <!-- Footer -->
                <div style="
                    padding:8px 22px 12px;
                    font-family:Orbitron,monospace;
                    font-size:.48rem; color:rgba(168,85,247,.5);
                    letter-spacing:1.5px; border-top:1px solid rgba(168,85,247,.12);
                ">
                    ● IMAGE → GEMINI VISION → TTS AUDIO PIPELINE · AEROMIND 2026
                </div>
            </div>
        `;
        // Auto-dismiss after 25s
        const timer = setTimeout(() => el.remove(), 25000);
        el.addEventListener('click', (e) => { if (e.target === el) { clearTimeout(timer); el.remove(); } });
    } else if (state === 'error') {
        el.innerHTML = `
            <div style="
                max-width:400px; background:rgba(20,5,5,0.97);
                border:1.5px solid #E10600; border-radius:6px;
                padding:24px; text-align:center; font-family:Orbitron,monospace;
            ">
                <div style="font-size:1.4rem;margin-bottom:12px;">⚠</div>
                <div style="color:#E10600;font-size:.7rem;letter-spacing:2px;font-weight:700;">ANALYSIS FAILED</div>
                <div style="color:rgba(255,255,255,.45);font-size:.55rem;margin-top:8px;">${text || 'Unknown error'}</div>
                <button id="vision-close" style="
                    margin-top:16px; background:var(--f1-red); border:none; color:#fff;
                    font-family:Orbitron,monospace; font-size:.55rem; padding:6px 16px;
                    border-radius:2px; cursor:pointer; letter-spacing:1px;
                ">DISMISS</button>
            </div>
        `;
    }

    // Inject keyframe animations once
    if (!document.getElementById('vision-keyframes')) {
        const style = document.createElement('style');
        style.id = 'vision-keyframes';
        style.textContent = `
            @keyframes vision-fade-in { from{opacity:0} to{opacity:1} }
            @keyframes vision-slide-in { from{transform:translateY(-30px);opacity:0} to{transform:translateY(0);opacity:1} }
            @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
            @keyframes pulse-violet {
                0%,100% { box-shadow:0 0 10px rgba(168,85,247,0.6),0 0 20px rgba(168,85,247,0.2); }
                50%      { box-shadow:0 0 18px rgba(168,85,247,0.95),0 0 36px rgba(168,85,247,0.45); }
            }
        `;
        document.head.appendChild(style);
    }

    document.body.appendChild(el);

    // Wire close button (for result + error states)
    el.querySelector('#vision-close')?.addEventListener('click', () => el.remove());
}

export class F1Track {
    constructor() {
        this._sampler    = null;
        this._carEls     = {};     // driver_number → SVG group
        this._lapFrac    = 0.08;   // leader's current track fraction (0–1, wraps around)
        this._lastDrvSet = '';     // detect session change → reset
        this._lastLeaderY = null;  // detect forward progress
        this._lastGapFrac = {};    // driver_number → smoothed gap fraction (prevents jumps)
    }

    render(containerId) {
        const container = document.getElementById(containerId);
        container.innerHTML = `
            <div class="f1-panel" style="height:100%;">
                <div class="f1-panel-header">
                    <span class="f1-panel-title">Live Circuit</span>
                    <div style="display:flex;gap:8px;align-items:center;">
                        <button id="track-analyse-btn" style="
                            background:linear-gradient(135deg,#7c3aed,#a855f7);
                            border:none;
                            color:#fff;
                            font-family:var(--font-hud);
                            font-size:.55rem;
                            font-weight:700;
                            letter-spacing:1.5px;
                            padding:5px 12px;
                            cursor:pointer;
                            border-radius:3px;
                            box-shadow:0 0 12px rgba(168,85,247,0.6),0 0 24px rgba(168,85,247,0.25);
                            animation:pulse-violet 2s ease-in-out infinite;
                        ">👁 ARIA VISION</button>
                        <span id="track-cars-count" class="badge badge-warn">0 CARS</span>
                    </div>
                </div>
                <div class="f1-panel-body" style="padding:0; position:relative; overflow:hidden;">
                    <div id="track-svg-container" style="width:100%;height:100%;overflow:hidden;">
                        <svg id="track-svg" width="100%" height="100%"
                             viewBox="0 0 800 550"
                             preserveAspectRatio="xMidYMid meet"
                             style="display:block;max-width:100%;max-height:100%;">

                            <!-- Defs: glow filters per team -->
                            <defs>
                                <filter id="glow-red">
                                    <feGaussianBlur stdDeviation="3" result="blur"/>
                                    <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
                                </filter>
                                <filter id="glow-blue">
                                    <feGaussianBlur stdDeviation="3" result="blur"/>
                                    <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
                                </filter>
                            </defs>

                            <!-- Track outline -->
                            <path id="track-path-outer" class="track-circuit" d="${CIRCUIT_D}"/>
                            <path id="track-path-inner" class="track-circuit-inner" d="${CIRCUIT_D}"/>

                            <!-- Start/Finish line -->
                            <line id="sf-line" x1="390" y1="38" x2="410" y2="62"
                                  stroke="white" stroke-width="2" opacity="0.6"/>
                            <text x="415" y="48" fill="rgba(255,255,255,0.4)"
                                  font-family="Orbitron" font-size="8" letter-spacing="1">S/F</text>

                            <!-- Battle arcs layer (rendered behind cars) -->
                            <g id="battle-arcs"></g>

                            <!-- Cars layer -->
                            <g id="cars-layer"></g>

                        </svg>
                    </div>

                    <!-- Legend -->
                    <div id="track-legend" style="
                        position:absolute; bottom:10px; left:12px;
                        font-size:.58rem; color:rgba(255,255,255,.4);
                        font-family:var(--font-hud); letter-spacing:1px;
                    "></div>
                </div>
            </div>
        `;

        // Build path sampler after DOM is ready
        requestAnimationFrame(() => {
            const pathEl = document.getElementById('track-path-outer');
            if (pathEl && pathEl.getTotalLength) {
                this._sampler = buildPathSampler(pathEl, 1000);
            }
        });

        // Wire up ARIA multimodal analyse button
        document.getElementById('track-analyse-btn').addEventListener('click', () => {
            this.analyseWithGemini();
        });
    }

    /**
     * Capture the live circuit SVG as a PNG and send to Gemini Vision.
     * Fix: clone SVG with explicit pixel dimensions so canvas renders correctly
     * (width="100%" resolves to 0 when serialized outside the document).
     */
    async analyseWithGemini() {
        const btn = document.getElementById('track-analyse-btn');
        if (btn) {
            btn.textContent = '⏳ ANALYSING...';
            btn.disabled = true;
            btn.style.animation = 'none';
            btn.style.background = 'rgba(168,85,247,0.25)';
            btn.style.boxShadow  = 'none';
        }

        _showVisionModal('loading');

        try {
            const svg = document.getElementById('track-svg');
            if (!svg) throw new Error('track-svg not found');

            // --- SVG → canvas fix ---
            // Clone so we can mutate attributes without touching the live DOM
            const clone = svg.cloneNode(true);
            clone.setAttribute('width',  '800');
            clone.setAttribute('height', '550');
            clone.setAttribute('xmlns',  'http://www.w3.org/2000/svg');
            // Inline a dark background rect so Gemini sees the dark theme
            const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            bg.setAttribute('width', '800'); bg.setAttribute('height', '550');
            bg.setAttribute('fill', '#0d0d1a');
            clone.insertBefore(bg, clone.firstChild);

            const svgData = new XMLSerializer().serializeToString(clone);
            const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
            const url     = URL.createObjectURL(svgBlob);

            const imageBase64 = await new Promise((resolve, reject) => {
                const img    = new Image();
                const canvas = document.createElement('canvas');
                canvas.width = 800; canvas.height = 550;
                const ctx = canvas.getContext('2d');

                img.onload = () => {
                    ctx.drawImage(img, 0, 0, 800, 550);
                    URL.revokeObjectURL(url);
                    resolve(canvas.toDataURL('image/png').split(',')[1]);
                };
                img.onerror = (e) => { URL.revokeObjectURL(url); reject(new Error('SVG render failed')); };
                img.src = url;
            });

            // POST to backend → Gemini Vision
            const res  = await fetch('/api/aria/analyse-frame', {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ image: imageBase64 }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            // Show prominent modal overlay
            _showVisionModal('result', data.commentary);

            // Dispatch to ARIA panel for feed entry + audio playback
            window.dispatchEvent(new CustomEvent('aria-frame-analysis', {
                detail: {
                    text:      data.commentary,
                    audio_b64: data.audio_b64,
                    mime_type: data.mime_type,
                },
            }));

        } catch (e) {
            console.error('analyseWithGemini error:', e);
            _showVisionModal('error', e.message);
        } finally {
            if (btn) {
            btn.textContent = '👁 ARIA VISION';
            btn.disabled = false;
            btn.style.animation = 'pulse-violet 2s ease-in-out infinite';
            btn.style.background = 'linear-gradient(135deg,#7c3aed,#a855f7)';
            btn.style.boxShadow  = '0 0 12px rgba(168,85,247,0.6),0 0 24px rgba(168,85,247,0.25)';
        }
        }
    }

    /**
     * Update the track with a fresh snapshot from /api/snapshot
     * snapshot = { cars: [...], edges: [...] }
     */
    update(snapshot) {
        if (!this._sampler) return;

        const cars  = snapshot.cars  || [];
        const edges = snapshot.edges || [];

        if (cars.length === 0) return;

        // Detect session change (different set of drivers) → full reset
        const drvSet = [...cars].map(c => c.driver_number).sort().join(',');
        if (drvSet !== this._lastDrvSet) {
            // Clear all existing car elements from SVG
            Object.values(this._carEls).forEach(el => el.remove());
            this._carEls      = {};
            this._lapFrac     = 0.08;
            this._lastLeaderY = null;
            this._lastGapFrac = {};
            this._lastDrvSet  = drvSet;
        }

        // Sort cars by track_pos (real sessions) or y (demo) — leader first
        const sorted = [...cars].sort(
            (a, b) => (b.track_pos || b.y || 0) - (a.track_pos || a.y || 0)
        );

        const leaderPos  = sorted[0]?.track_pos || sorted[0]?.y || 0;
        const lastCar    = sorted[sorted.length - 1];
        const lastPos    = lastCar?.track_pos || lastCar?.y || 0;
        // Total field spread in metres (gap from leader to last car)
        // Use 300m as reference spread so 1 full gap = ~30% of track
        const fieldSpread = Math.max(leaderPos - lastPos, 60);

        // Advance the leader's lap fraction — detect forward progress from data
        if (this._lastLeaderY !== null) {
            const delta = leaderPos - this._lastLeaderY;
            if (delta > 0) {
                // Real data moved forward — advance proportionally (assume ~5000m lap)
                this._lapFrac += delta / 5000;
            } else {
                // Demo oscillates or no progress — always tick forward at constant rate
                this._lapFrac += 0.004;
            }
        } else {
            this._lapFrac += 0.004;
        }
        this._lastLeaderY = leaderPos;
        // Wrap 0–1
        this._lapFrac = ((this._lapFrac % 1) + 1) % 1;

        const carsLayer  = document.getElementById('cars-layer');
        const battleArcs = document.getElementById('battle-arcs');
        if (!carsLayer || !battleArcs) return;

        const trackCount = document.getElementById('track-cars-count');
        if (trackCount) {
            trackCount.textContent = `${cars.length} CARS`;
            trackCount.className = 'badge badge-live';
        }

        // --- Draw cars ---
        const carPositions = {};  // drv → {x, y, pos} for arc drawing

        sorted.forEach((car, rank) => {
            const drv  = car.driver_number;
            const team = car.team || '';
            const color = teamColor(team);

            // Gap from leader in position units; scale so full field ≈ 12.5% of lap
            const carPos        = car.track_pos || car.y || 0;
            const gapFromLeader = leaderPos - carPos;
            const rawGapFrac    = gapFromLeader / (fieldSpread * 8);
            // Smooth gap fraction — lerp 15% toward target each tick to prevent jumps
            const prevGapFrac   = this._lastGapFrac[drv] ?? rawGapFrac;
            const gapFrac       = prevGapFrac + (rawGapFrac - prevGapFrac) * 0.15;
            this._lastGapFrac[drv] = gapFrac;
            // Leader is at _lapFrac; each car behind is offset backwards on path
            const frac = ((this._lapFrac - gapFrac) % 1 + 1) % 1;
            const pt   = getPositionOnPath(this._sampler, frac);
            carPositions[drv] = { x: pt.x, y: pt.y, rank, frac };

            // Create or update marker
            let g = this._carEls[drv];
            if (!g) {
                g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
                g.classList.add('car-marker');
                g.setAttribute('data-drv', drv);
                g.innerHTML = `
                    <circle r="9" fill="${color}" stroke="#000" stroke-width="1.5" opacity="0.92"/>
                    <text text-anchor="middle" dominant-baseline="central"
                          font-family="Orbitron" font-weight="700" font-size="7"
                          fill="white">${drv}</text>
                    <title>${car.driver_name || drv} (${team})</title>
                `;
                carsLayer.appendChild(g);
                this._carEls[drv] = g;
                // Set initial position
                g.setAttribute('transform', `translate(${pt.x},${pt.y})`);
            } else {
                // Animate to new position with GSAP
                gsap.to(g, {
                    duration: 1.5,
                    ease: 'power2.out',
                    attr: { transform: `translate(${pt.x},${pt.y})` },
                });

                // Update color if team changed
                const circle = g.querySelector('circle');
                if (circle) circle.setAttribute('fill', color);
            }

            // OVT glow
            const circle = g.querySelector('circle');
            if (circle) {
                if (car.overtake_mode_active) {
                    circle.setAttribute('stroke', '#FF8000');
                    circle.setAttribute('stroke-width', '3');
                    gsap.to(circle, { duration: 0.5, attr: { r: 11 }, yoyo: true, repeat: -1 });
                } else {
                    gsap.killTweensOf(circle);
                    circle.setAttribute('stroke', '#000');
                    circle.setAttribute('stroke-width', '1.5');
                    circle.setAttribute('r', '9');
                }
            }

            // Rank label (P1, P2...)
            const txt = g.querySelector('text');
            if (txt) txt.textContent = drv;
        });

        // Remove stale car markers
        Object.keys(this._carEls).forEach(drv => {
            if (!cars.find(c => c.driver_number == drv)) {
                this._carEls[drv].remove();
                delete this._carEls[drv];
            }
        });

        // --- Draw battle arcs ---
        battleArcs.innerHTML = '';
        edges.forEach(edge => {
            const a = carPositions[edge.from];
            const b = carPositions[edge.to];
            if (!a || !b) return;

            const isOVT  = edge.type === 'OVERTAKE_MODE_ELIGIBLE';
            const cls    = isOVT ? 'ovt-arc' : 'battle-arc';
            const dx     = b.x - a.x;
            const dy     = b.y - a.y;
            const mid_x  = (a.x + b.x) / 2 + (-dy * 0.25);
            const mid_y  = (a.y + b.y) / 2 + (dx * 0.25);

            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('class', cls);
            path.setAttribute('d', `M ${a.x},${a.y} Q ${mid_x},${mid_y} ${b.x},${b.y}`);
            battleArcs.appendChild(path);
        });

        // --- Update legend ---
        const legend = document.getElementById('track-legend');
        if (legend) {
            legend.innerHTML = sorted.slice(0, 5).map((c, i) => {
                const col = teamColor(c.team);
                return `<span style="color:${col};margin-right:8px;">P${i+1} ${c.driver_name || c.driver_number}</span>`;
            }).join('');
        }
    }
}
