/**
 * TelemetryPanel.js — Driver standings + live SoC/speed telemetry
 * Fully dynamic — all data from /api/snapshot, no hardcoded driver info
 */

import { gsap } from 'gsap';

// Team color lookup — matches F1Track.js
const TEAM_COLORS = {
    'Red Bull':     '#3671C6',
    'Ferrari':      '#E8002D',
    'McLaren':      '#FF8000',
    'Mercedes':     '#27F4D2',
    'Alpine':       '#FF69B4',
    'Williams':     '#64C4FF',
    'Haas':         '#B6BABD',
    'Sauber':       '#00E64D',
    'Aston Martin': '#358C75',
    'VCARB':        '#2B4562',
};

function teamColor(team) { return TEAM_COLORS[team] || '#888'; }

// ---------------------------------------------------------------------------
// SoC Detail Modal — shown when user clicks a driver card
// ---------------------------------------------------------------------------
function showSoCModal(car, allCars, is2026) {
    document.getElementById('soc-modal')?.remove();

    const soc     = Math.round((car.battery_soc || 0) * 100);
    const spd     = Math.round(car.speed || 0);
    const color   = TEAM_COLORS[car.team] || '#888';
    const name    = (car.driver_name || `CAR ${car.driver_number}`).toUpperCase();
    const isOVT   = car.overtake_mode_active;

    // Zone config
    const zones = [
        { label: 'CRITICAL', min: 0,  max: 30,  color: '#E10600', desc: 'Cannot deploy OVT. Engine running on reserve.' },
        { label: 'LOW',      min: 30, max: 50,  color: '#FF8000', desc: 'Limited deployment. Avoid prolonged attacks.' },
        { label: 'GOOD',     min: 50, max: 75,  color: '#FFD700', desc: 'Normal racing. Selective deployment available.' },
        { label: 'OPTIMAL',  min: 75, max: 100, color: '#27F4D2', desc: 'Full Overtake Override available. Full attack.' },
    ];
    const currentZone = zones.find(z => soc >= z.min && soc < z.max) || zones[3];

    // Sorted list for comparison bar
    const sorted = [...allCars].sort((a,b) => (b.battery_soc||0) - (a.battery_soc||0));

    // Build zone rows
    const zoneRows = zones.slice().reverse().map(z => {
        const active = z.label === currentZone.label;
        const fill   = Math.min(100, Math.max(0, ((Math.min(soc, z.max) - z.min) / (z.max - z.min)) * 100));
        return `
        <div style="display:flex;align-items:center;gap:8px;padding:5px 0;
                    ${active ? `background:rgba(${hexToRgbM(z.color)},.08);border-radius:3px;padding:5px 6px;` : ''}">
            <div style="width:6px;height:6px;border-radius:50%;background:${z.color};flex-shrink:0;
                        ${active ? 'box-shadow:0 0 6px '+z.color : ''}"></div>
            <div style="flex:1;">
                <div style="display:flex;justify-content:space-between;
                            font-family:var(--font-hud);font-size:.5rem;
                            color:${active ? z.color : 'rgba(255,255,255,.35)'};
                            letter-spacing:1px;margin-bottom:3px;">
                    <span>${z.label} ${z.min}–${z.max}%</span>
                    ${active ? `<span style="font-size:.45rem;color:${z.color};">◀ YOU ARE HERE</span>` : ''}
                </div>
                <div style="height:2px;background:rgba(255,255,255,.08);border-radius:1px;">
                    <div style="height:100%;width:${active ? soc - z.min <= 0 ? 0 : Math.min(100,(soc-z.min)/(z.max-z.min)*100) : (soc > z.max ? 100 : 0)}%;
                                background:${z.color};border-radius:1px;"></div>
                </div>
                ${active ? `<div style="font-family:var(--font-f1);font-size:.52rem;
                                        color:rgba(255,255,255,.5);margin-top:3px;">${z.desc}</div>` : ''}
            </div>
        </div>`;
    }).join('');

    // Comparison table — all drivers sorted by SoC
    const maxSoC = Math.max(...sorted.map(c => Math.round((c.battery_soc||0)*100)), 1);
    const compBars = sorted.map((c, i) => {
        const cs     = Math.round((c.battery_soc || 0) * 100);
        const cc     = TEAM_COLORS[c.team] || '#888';
        const cspd   = Math.round(c.speed || 0);
        const cn     = (c.driver_name || `${c.driver_number}`).toUpperCase().split(' ').pop();
        const isSelf = c.driver_number === car.driver_number;
        const hasOVT = c.overtake_mode_active;
        // Color the bar by zone
        const barCol = cs < 30 ? '#E10600' : cs < 50 ? '#FF8000' : cs < 75 ? '#FFD700' : '#27F4D2';
        const barW   = Math.round((cs / maxSoC) * 100); // normalize to widest bar = 100%
        return `
        <div style="
            display:grid;
            grid-template-columns:20px 58px 1fr 32px 52px;
            align-items:center;gap:5px;padding:4px 6px;border-radius:3px;
            ${isSelf ? `background:rgba(${hexToRgbM(cc)},.1);border:1px solid rgba(${hexToRgbM(cc)},.25);` : 'border:1px solid transparent;'}
        ">
            <div style="font-family:var(--font-hud);font-size:.42rem;
                        color:rgba(255,255,255,.3);">${i+1}</div>
            <div>
                <div style="font-family:var(--font-hud);font-size:.5rem;
                            color:${isSelf ? cc : 'rgba(255,255,255,.55)'};
                            font-weight:${isSelf ? '700' : '400'};
                            white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${cn}</div>
                <div style="font-family:var(--font-hud);font-size:.38rem;
                            color:rgba(255,255,255,.2);">#${c.driver_number}</div>
            </div>
            <div style="display:flex;flex-direction:column;gap:2px;">
                <div style="height:5px;background:rgba(255,255,255,.07);border-radius:2px;overflow:hidden;">
                    <div style="height:100%;width:${barW}%;background:${isSelf ? cc : barCol};
                                border-radius:2px;transition:width .6s ease;
                                ${isSelf ? `box-shadow:0 0 6px ${cc};` : ''}"></div>
                </div>
                <div style="font-family:var(--font-hud);font-size:.36rem;color:${barCol};">
                    ${cs < 30 ? 'CRITICAL' : cs < 50 ? 'LOW' : cs < 75 ? 'GOOD' : 'OPTIMAL'}
                </div>
            </div>
            <div style="font-family:var(--font-hud);font-size:.52rem;font-weight:700;
                        color:${isSelf ? cc : barCol};text-align:right;">${cs}%</div>
            <div style="font-family:var(--font-hud);font-size:.4rem;
                        color:rgba(255,255,255,.25);text-align:right;">
                ${hasOVT ? `<span style="color:#FF8000;font-size:.42rem;">⚡OVT</span>` : `${cspd}km/h`}
            </div>
        </div>`;
    }).join('');

    const modal = document.createElement('div');
    modal.id = 'soc-modal';
    modal.style.cssText = `
        position:fixed;inset:0;z-index:9999;
        display:flex;align-items:center;justify-content:center;
        background:rgba(0,0,0,.72);backdrop-filter:blur(6px);
        -webkit-backdrop-filter:blur(6px);animation:fadeIn .25s ease;
    `;
    modal.innerHTML = `
        <div style="
            background:#0a0a0f;
            border:1px solid ${color};
            border-radius:6px;
            padding:0;
            width:520px;max-width:95vw;
            max-height:88vh;overflow-y:auto;
            box-shadow:0 0 40px rgba(${hexToRgbM(color)},.2);
        ">
            <!-- Header -->
            <div style="
                padding:16px 20px;
                background:rgba(${hexToRgbM(color)},.1);
                border-bottom:1px solid rgba(${hexToRgbM(color)},.25);
                display:flex;justify-content:space-between;align-items:center;
            ">
                <div>
                    <div style="font-family:var(--font-hud);font-size:.4rem;
                                color:rgba(255,255,255,.3);letter-spacing:2px;margin-bottom:4px;">
                        DRIVER ENERGY DETAIL
                    </div>
                    <div style="display:flex;align-items:baseline;gap:10px;">
                        <span style="font-family:var(--font-hud);font-weight:900;
                                     font-size:1.6rem;color:${color};">#${car.driver_number}</span>
                        <span style="font-family:var(--font-hud);font-size:.9rem;
                                     font-weight:700;color:#fff;">${name}</span>
                        ${isOVT ? `<span style="font-family:var(--font-hud);font-size:.5rem;
                                              color:#FF8000;letter-spacing:2px;
                                              border:1px solid #FF8000;padding:2px 6px;
                                              border-radius:2px;">⚡ OVT ACTIVE</span>` : ''}
                    </div>
                    <div style="font-family:var(--font-hud);font-size:.5rem;
                                color:rgba(255,255,255,.3);letter-spacing:1px;margin-top:2px;">
                        ${(car.team||'').toUpperCase()} · ${spd} KM/H
                    </div>
                </div>
                <!-- Big SoC number -->
                <div style="text-align:center;">
                    <div style="font-family:var(--font-hud);font-size:2.8rem;font-weight:900;
                                color:${currentZone.color};line-height:1;
                                text-shadow:0 0 20px ${currentZone.color};">${soc}</div>
                    <div style="font-family:var(--font-hud);font-size:.5rem;
                                color:${currentZone.color};letter-spacing:2px;">% SoC</div>
                    <div style="font-family:var(--font-hud);font-size:.45rem;
                                color:${currentZone.color};letter-spacing:1px;margin-top:2px;
                                opacity:.8;">${currentZone.label}</div>
                </div>
            </div>

            <div style="padding:16px 20px;display:flex;flex-direction:column;gap:16px;">

                <!-- What is SoC? -->
                <div style="
                    background:rgba(255,255,255,.03);border-radius:4px;
                    padding:12px 14px;border-left:3px solid rgba(39,244,210,.4);
                ">
                    <div style="font-family:var(--font-hud);font-size:.45rem;
                                color:rgba(39,244,210,.6);letter-spacing:2px;margin-bottom:6px;">
                        WHAT IS STATE OF CHARGE?
                    </div>
                    <div style="font-family:var(--font-f1);font-size:.62rem;
                                color:rgba(255,255,255,.7);line-height:1.7;">
                        In the 2026 F1 regulations, every car carries a <strong style="color:#fff;">
                        high-voltage battery</strong> (≈ 350 kWh) powering an electric motor
                        on the rear axle. <strong style="color:#fff;">SoC (State of Charge)</strong>
                        is how full that battery is — 100% = fully charged, 0% = depleted.
                    </div>
                    <div style="font-family:var(--font-f1);font-size:.6rem;
                                color:rgba(255,255,255,.5);line-height:1.7;margin-top:6px;">
                        When a driver activates <strong style="color:#FF8000;">Overtake Override Mode</strong>,
                        the electric motor fires at maximum power, giving a burst of extra speed —
                        but it rapidly drains the battery. Strategy is all about managing when to deploy.
                    </div>
                </div>

                <!-- Zone chart -->
                <div>
                    <div style="font-family:var(--font-hud);font-size:.45rem;
                                color:rgba(255,255,255,.3);letter-spacing:2px;margin-bottom:8px;">
                        ENERGY ZONES
                    </div>
                    ${zoneRows}
                </div>

                <!-- Grid comparison -->
                <div>
                    <div style="font-family:var(--font-hud);font-size:.45rem;
                                color:rgba(255,255,255,.3);letter-spacing:2px;margin-bottom:8px;">
                        GRID COMPARISON — BATTERY STATE
                    </div>
                    <div style="display:flex;flex-direction:column;gap:5px;">
                        ${compBars}
                    </div>
                </div>

                <!-- 2026 rule note -->
                <div style="font-family:var(--font-hud);font-size:.42rem;
                            color:rgba(255,255,255,.15);letter-spacing:1px;
                            text-align:center;padding-top:4px;">
                    FIA F1 2026 TECHNICAL REGULATIONS · HYBRID POWER UNIT · ARTICLE 5.4
                </div>
            </div>

            <!-- Close -->
            <div style="padding:10px 20px;border-top:1px solid rgba(255,255,255,.05);text-align:center;">
                <button id="soc-modal-close" style="
                    background:none;border:1px solid rgba(255,255,255,.15);
                    color:rgba(255,255,255,.4);font-family:var(--font-hud);
                    font-size:.5rem;letter-spacing:2px;padding:6px 24px;
                    border-radius:3px;cursor:pointer;
                ">CLOSE</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    modal.addEventListener('click', e => { if (e.target === modal) modal.remove(); });
    document.getElementById('soc-modal-close')?.addEventListener('click', () => modal.remove());
}

function hexToRgbM(hex) {
    if (!hex || hex[0] !== '#') return '255,255,255';
    const r = parseInt(hex.slice(1,3),16);
    const g = parseInt(hex.slice(3,5),16);
    const b = parseInt(hex.slice(5,7),16);
    return `${r},${g},${b}`;
}

export class TelemetryPanel {
    constructor() {
        this._bodyEl           = null;
        this._cards            = {};   // driver_number → card element
        this._snapshot         = null; // latest full snapshot for modal
        this._placeholderGone  = false;
    }

    render(containerId) {
        const container = document.getElementById(containerId);
        container.innerHTML = `
            <div class="f1-panel" style="height:100%;">
                <div class="f1-panel-header">
                    <span class="f1-panel-title">Pit Wall Telemetry</span>
                    <span class="badge badge-live">LIVE</span>
                </div>
                <div class="f1-panel-body" id="telemetry-body">
                    <div style="color:rgba(255,255,255,.2);font-size:.7rem;text-align:center;padding:20px 0;">
                        Waiting for telemetry...
                    </div>
                </div>

                <!-- Battle alert row -->
                <div id="battle-alert" style="
                    display:none; padding:8px 12px;
                    background:rgba(225,6,0,0.15);
                    border-top:1px solid rgba(225,6,0,0.3);
                    font-family:var(--font-hud); font-size:.6rem;
                    color:var(--f1-red); letter-spacing:2px;
                    animation:livePulse 1s infinite;
                "></div>
            </div>
        `;
        this._bodyEl = document.getElementById('telemetry-body');
    }

    /**
     * Update with snapshot data from /api/snapshot
     * snapshot = { cars: [...], edges: [...], is_2026_regs: bool }
     */
    update(snapshot) {
        this._snapshot = snapshot;  // keep for modal
        const cars       = (snapshot.cars  || []).sort((a, b) => (b.y || 0) - (a.y || 0));
        const edges      = snapshot.edges || [];
        const is2026     = snapshot.is_2026_regs !== false;  // default true (demo)

        if (cars.length === 0) return;

        // Build attacking pairs set for highlight
        const attackingDrvs = new Set(edges.map(e => e.from));
        const ovtDrvs       = new Set(
            edges.filter(e => e.type === 'OVERTAKE_MODE_ELIGIBLE').map(e => e.from)
        );

        cars.forEach((car, rank) => {
            const drv  = car.driver_number;
            const name = car.driver_name || `CAR ${drv}`;
            const team = car.team || 'Unknown';
            const soc  = Math.round((car.battery_soc || 0) * 100);
            const spd  = Math.round(car.speed || 0);
            const isOVT    = ovtDrvs.has(drv);
            const isAttack = attackingDrvs.has(drv);
            const color    = teamColor(team);

            let card = this._cards[drv];
            if (!card) {
                card = document.createElement('div');
                card.className = 'driver-card';
                card.id = `dc-${drv}`;
                card.title = 'Click for energy detail';
                card.style.cursor = 'pointer';
                card.addEventListener('click', () => {
                    const snap  = this._snapshot;
                    const carData = (snap?.cars || []).find(c => c.driver_number === drv);
                    if (carData) showSoCModal(carData, snap.cars || [], snap?.is_2026_regs !== false);
                });
                const barLabel = is2026 ? 'SOC' : 'DRS';
                card.innerHTML = `
                    <div class="dc-top">
                        <span class="dc-pos" id="dc-pos-${drv}">P${rank+1}</span>
                        <span class="dc-name" id="dc-name-${drv}"
                              style="color:${color}">${name.toUpperCase()}</span>
                        <span class="dc-num">#${drv}</span>
                        <span class="ovt-tag" id="dc-ovt-${drv}"
                              style="display:none;">${is2026 ? 'OVT' : 'DRS'}</span>
                    </div>
                    <div style="font-size:.55rem;color:rgba(255,255,255,.3);
                                font-family:var(--font-hud);letter-spacing:1px;
                                margin-bottom:5px;">${team.toUpperCase()}</div>

                    <!-- SoC / DRS Bar -->
                    <div class="soc-row">
                        <span class="soc-label">${barLabel}</span>
                        <div class="soc-track">
                            <div class="soc-fill" id="soc-fill-${drv}"
                                 style="width:${soc}%"></div>
                        </div>
                        <span class="soc-val" id="soc-val-${drv}">${is2026 ? soc + '%' : (soc > 50 ? 'OPEN' : 'CLOSED')}</span>
                    </div>

                    <!-- Speed -->
                    <div style="display:flex;justify-content:space-between;
                                margin-top:5px;align-items:center;">
                        <span style="font-size:.55rem;color:rgba(255,255,255,.3);
                                     font-family:var(--font-hud);letter-spacing:1px;">SPD</span>
                        <span class="speed-val" id="spd-val-${drv}">${spd} km/h</span>
                    </div>
                    ${is2026 ? `<div style="font-family:var(--font-hud);font-size:.38rem;
                                            color:rgba(255,255,255,.18);letter-spacing:1px;
                                            margin-top:4px;text-align:right;">
                                    TAP FOR ENERGY DETAIL ↗
                                </div>` : ''}
                `;
                card.style.borderLeftColor = color;
                if (!this._placeholderGone) {
                    this._bodyEl.innerHTML = '';
                    this._placeholderGone = true;
                }
                this._bodyEl.appendChild(card);
                this._cards[drv] = card;
            } else {
                // Update existing card values with GSAP for smooth transition
                const posEl  = document.getElementById(`dc-pos-${drv}`);
                const sncFill = document.getElementById(`soc-fill-${drv}`);
                const socVal = document.getElementById(`soc-val-${drv}`);
                const spdVal = document.getElementById(`spd-val-${drv}`);

                if (posEl)   posEl.textContent   = `P${rank+1}`;
                if (socVal)  socVal.textContent  = is2026 ? `${soc}%` : (soc > 50 ? 'OPEN' : 'CLOSED');
                if (spdVal)  spdVal.textContent  = `${spd} km/h`;

                if (sncFill) {
                    gsap.to(sncFill, {
                        width: `${soc}%`,
                        duration: 1.2, ease: 'power2.out',
                    });
                    // Color the bar based on SoC
                    sncFill.className = 'soc-fill' +
                        (soc < 30 ? ' crit' : soc < 45 ? ' warn' : '');
                }
            }

            // Battle / OVT state
            const ovtTag = document.getElementById(`dc-ovt-${drv}`);
            if (ovtTag) {
                ovtTag.style.display = isOVT ? 'inline-block' : 'none';
            }
            if (isOVT) {
                card.className = 'driver-card ovt';
                card.style.borderLeftColor = '#FF8000';
            } else if (isAttack) {
                card.className = 'driver-card battle';
            } else {
                card.className = 'driver-card';
                card.style.borderLeftColor = color;
            }
        });

        // Remove cards for drivers no longer in the snapshot
        Object.keys(this._cards).forEach(drv => {
            if (!cars.find(c => c.driver_number == drv)) {
                this._cards[drv].remove();
                delete this._cards[drv];
            }
        });

        // Re-sort card DOM order to match current race position
        // (appendChild on an already-attached node moves it — no clone needed)
        cars.forEach(car => {
            const c = this._cards[car.driver_number];
            if (c) this._bodyEl.appendChild(c);
        });

        // Battle alert
        const alertEl = document.getElementById('battle-alert');
        if (alertEl) {
            const ovtEdges = edges.filter(e => e.type === 'OVERTAKE_MODE_ELIGIBLE');
            if (ovtEdges.length > 0) {
                const e = ovtEdges[0];
                const aC = cars.find(c => c.driver_number === e.from);
                const dC = cars.find(c => c.driver_number === e.to);
                const aName = aC?.driver_name || `CAR ${e.from}`;
                const dName = dC?.driver_name || `CAR ${e.to}`;
                alertEl.style.display = 'block';
                alertEl.textContent   = `⚡ OVT MODE — ${aName} vs ${dName}`;
            } else if (edges.some(e => e.type === 'ATTACKING')) {
                const e = edges.find(e => e.type === 'ATTACKING');
                const aC = cars.find(c => c.driver_number === e.from);
                const dC = cars.find(c => c.driver_number === e.to);
                const aName = aC?.driver_name || `CAR ${e.from}`;
                const dName = dC?.driver_name || `CAR ${e.to}`;
                alertEl.style.display = 'block';
                alertEl.style.color   = 'rgba(255,255,255,.6)';
                alertEl.textContent   = `ATTACKING — ${aName} → ${dName}`;
            } else {
                alertEl.style.display = 'none';
            }
        }
    }
}
