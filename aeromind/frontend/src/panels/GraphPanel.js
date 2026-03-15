/**
 * GraphPanel.js — Battle Intelligence Board
 * Replaces D3 force graph with a clean HTML panel showing live battle data from Memgraph.
 * No SVG/D3 sizing issues — pure HTML/CSS.
 */

const TEAM_COLORS = {
    'Red Bull':     '#3671C6', 'Ferrari':      '#E8002D',
    'McLaren':      '#FF8000', 'Mercedes':     '#27F4D2',
    'Alpine':       '#FF69B4', 'Williams':     '#64C4FF',
    'Haas':         '#B6BABD', 'Sauber':       '#00E64D',
    'Aston Martin': '#358C75', 'VCARB':        '#2B4562',
};
const C = (t) => TEAM_COLORS[t] || '#AAAAAA';

export class GraphPanel {
    constructor() {
        this._bodyEl = null;
        this._decEl  = null;
    }

    render(containerId) {
        document.getElementById(containerId).innerHTML = `
            <div class="f1-panel" style="height:100%;">
                <div class="f1-panel-header">
                    <span class="f1-panel-title">Memgraph — Battle Intelligence</span>
                    <span id="graph-badge" class="badge badge-warn">LOADING</span>
                </div>

                <!-- Gemini AI Situation Brief -->
                <div id="graph-situation" style="
                    padding:8px 12px;flex-shrink:0;
                    background:linear-gradient(135deg,rgba(39,244,210,.08),rgba(39,244,210,.02));
                    border-bottom:1px solid rgba(39,244,210,.15);
                ">
                    <div style="font-family:var(--font-hud);font-size:.42rem;color:rgba(39,244,210,.5);
                                letter-spacing:2px;margin-bottom:4px;">✦ GEMINI AI RACE BRIEF</div>
                    <div id="graph-sit-line1" style="font-family:var(--font-hud);font-size:.65rem;
                                                      font-weight:700;color:#fff;letter-spacing:1px;">
                        AWAITING RACE DATA...</div>
                    <div id="graph-sit-line2" style="font-family:var(--font-f1);font-size:.62rem;
                                                      color:rgba(255,255,255,.6);margin-top:2px;"></div>
                    <div id="graph-sit-line3" style="font-family:var(--font-f1);font-size:.6rem;font-style:italic;
                                                      color:rgba(39,244,210,.7);margin-top:2px;"></div>
                </div>

                <div class="f1-panel-body" id="graph-body" style="padding:8px;display:flex;flex-direction:column;gap:6px;">
                    <div style="color:rgba(255,255,255,.2);font-size:.7rem;text-align:center;padding:20px 0;">
                        Waiting for battle data...
                    </div>
                </div>
                <div id="graph-decisions" style="
                    padding:6px 10px;flex-shrink:0;
                    border-top:1px solid rgba(255,255,255,0.06);
                    max-height:72px;overflow-y:auto;
                    font-family:var(--font-f1);font-size:.62rem;
                    color:rgba(39,244,210,.7);line-height:1.5;
                "></div>
                <div style="padding:3px 10px 4px;flex-shrink:0;
                            font-family:var(--font-hud);font-size:.4rem;
                            color:rgba(255,255,255,.1);letter-spacing:1px;text-align:center;">
                    Memgraph → ADK Pit Wall → Gemini AI → ARIA Voice
                </div>
            </div>
        `;
        this._bodyEl = document.getElementById('graph-body');
        this._decEl  = document.getElementById('graph-decisions');
        this._pollSituation();
        setInterval(() => this._pollSituation(), 20000);
    }

    async _pollSituation() {
        if (document.hidden) return;   // tab not visible → skip (heartbeat also stopped)
        try {
            const res  = await fetch('/api/aria/situation');
            if (!res.ok) return;
            const data = await res.json();
            const lines = data.lines || [];
            const l1 = document.getElementById('graph-sit-line1');
            const l2 = document.getElementById('graph-sit-line2');
            const l3 = document.getElementById('graph-sit-line3');
            if (l1) l1.textContent = (lines[0] || '').toUpperCase();
            if (l2) l2.textContent = lines[1] || '';
            if (l3) l3.textContent = lines[2] || '';
        } catch {}
    }

    update({ nodes: rn = [], links: rl = [] }) {
        if (!this._bodyEl) return;

        const carNodes = rn.filter(n => n.node_type !== 'decision');
        const decNodes = rn.filter(n => n.node_type === 'decision');
        const battles  = rl.filter(l => l.type !== 'DECIDED_ON');

        // Update badge
        const badge = document.getElementById('graph-badge');
        if (badge) {
            badge.textContent = `${carNodes.length} CARS · ${battles.length} BATTLES`;
            badge.className   = battles.length > 0 ? 'badge badge-live' : 'badge badge-warn';
        }

        if (carNodes.length === 0) return;

        // Build car lookup — graph nodes use 'label' for name, battery_soc is already %
        const byId = {};
        carNodes.forEach(n => { byId[n.id] = n; });

        // Render battle pairs — group by unique pair
        const seen = new Set();
        const pairs = [];
        battles.forEach(l => {
            const sId = typeof l.source === 'object' ? l.source.id : l.source;
            const tId = typeof l.target === 'object' ? l.target.id : l.target;
            const key = `${sId}|${tId}`;
            if (!seen.has(key)) {
                seen.add(key);
                const atk = byId[sId];
                const def = byId[tId];
                if (atk && def) pairs.push({ atk, def, type: l.type });
            }
        });

        // Build HTML
        let html = '';

        if (pairs.length === 0) {
            // No active battles — show car grid
            html = `<div style="font-family:var(--font-hud);font-size:.52rem;color:rgba(255,255,255,.25);
                                letter-spacing:2px;text-align:center;padding:8px 0 4px;">
                        NO ACTIVE BATTLES
                    </div>`;
            // Show top-6 cars in a compact grid
            const sorted = [...carNodes].sort((a,b) => (b.track_pos||b.y||0)-(a.track_pos||a.y||0));
            html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;">`;
            sorted.slice(0,6).forEach((c, i) => {
                const soc  = c.battery_soc > 1 ? Math.round(c.battery_soc) : Math.round((c.battery_soc||0)*100);
                const col  = C(c.team);
                const name = (c.label || c.driver_name || `Car ${c.driver_number}`).toUpperCase();
                html += `
                    <div style="background:var(--f1-dark);border-left:3px solid ${col};
                                border-radius:0 3px 3px 0;padding:5px 8px;">
                        <div style="font-family:var(--font-hud);font-size:.58rem;
                                    font-weight:700;color:${col};">P${i+1} ${name}</div>
                        <div style="font-family:var(--font-hud);font-size:.5rem;
                                    color:rgba(255,255,255,.35);">SoC ${soc}%</div>
                    </div>`;
            });
            html += `</div>`;
        } else {
            pairs.forEach(({ atk, def, type }) => {
                const isOVT   = type === 'OVERTAKE_MODE_ELIGIBLE';
                const aCol    = C(atk.team);
                const dCol    = C(def.team);
                // graph nodes: name is in 'label', soc is already integer %
                const aName   = (atk.label || atk.driver_name || `Car ${atk.driver_number}`).toUpperCase();
                const dName   = (def.label || def.driver_name || `Car ${def.driver_number}`).toUpperCase();
                const aSoC    = atk.battery_soc > 1 ? Math.round(atk.battery_soc) : Math.round((atk.battery_soc||0)*100);
                const dSoC    = def.battery_soc > 1 ? Math.round(def.battery_soc) : Math.round((def.battery_soc||0)*100);
                const borderCol = isOVT ? '#FF8000' : '#E10600';
                const label     = isOVT ? '⚡ OVT MODE' : '↑ ATTACKING';

                const aTeam = (atk.team||'').toUpperCase();
                const dTeam = (def.team||'').toUpperCase();
                html += `
                <div style="background:rgba(255,255,255,0.03);
                            border:1px solid ${borderCol};border-radius:3px;
                            padding:7px 10px;${isOVT ? `box-shadow:0 0 8px rgba(255,128,0,0.25);` : ''}">
                    <div style="font-family:var(--font-hud);font-size:.5rem;
                                color:${borderCol};letter-spacing:2px;margin-bottom:6px;
                                display:flex;justify-content:space-between;align-items:center;">
                        <span>${label}</span>
                        ${isOVT ? `<span style="font-size:.42rem;color:rgba(255,128,0,.7);">BOOST ARMED</span>` : ''}
                    </div>
                    <div style="display:flex;align-items:stretch;gap:8px;">
                        <!-- Attacker -->
                        <div style="flex:1;background:rgba(${hexToRgb(aCol)},.12);
                                    border:1px solid ${aCol};border-radius:2px;padding:6px 8px;">
                            <div style="display:flex;align-items:baseline;gap:5px;margin-bottom:3px;">
                                <span style="font-family:var(--font-hud);font-weight:900;font-size:.9rem;
                                             color:${aCol};">#${atk.driver_number}</span>
                                <span style="font-family:var(--font-hud);font-size:.65rem;
                                             font-weight:700;color:#fff;">${aName}</span>
                            </div>
                            <div style="font-family:var(--font-hud);font-size:.45rem;
                                        color:rgba(255,255,255,.35);letter-spacing:1px;">${aTeam}</div>
                            <div style="margin-top:4px;">
                                <div style="display:flex;justify-content:space-between;align-items:center;
                                            font-family:var(--font-hud);font-size:.48rem;">
                                    <span style="color:rgba(255,255,255,.4);">SoC</span>
                                    <span style="color:${aSoC < 35 ? '#E10600' : aSoC < 50 ? '#FF8000' : '#27F4D2'};
                                                 font-weight:700;">${aSoC}%</span>
                                </div>
                                <div style="height:3px;background:rgba(255,255,255,.1);border-radius:2px;margin-top:2px;">
                                    <div style="height:100%;width:${aSoC}%;
                                                background:${aSoC < 35 ? '#E10600' : aSoC < 50 ? '#FF8000' : '#27F4D2'};
                                                border-radius:2px;"></div>
                                </div>
                            </div>
                        </div>
                        <!-- Arrow -->
                        <div style="display:flex;align-items:center;flex-shrink:0;">
                            <span style="font-size:1.3rem;color:${borderCol};">→</span>
                        </div>
                        <!-- Defender -->
                        <div style="flex:1;background:rgba(${hexToRgb(dCol)},.12);
                                    border:1px solid ${dCol};border-radius:2px;padding:6px 8px;">
                            <div style="display:flex;align-items:baseline;gap:5px;margin-bottom:3px;">
                                <span style="font-family:var(--font-hud);font-weight:900;font-size:.9rem;
                                             color:${dCol};">#${def.driver_number}</span>
                                <span style="font-family:var(--font-hud);font-size:.65rem;
                                             font-weight:700;color:#fff;">${dName}</span>
                            </div>
                            <div style="font-family:var(--font-hud);font-size:.45rem;
                                        color:rgba(255,255,255,.35);letter-spacing:1px;">${dTeam}</div>
                            <div style="margin-top:4px;">
                                <div style="display:flex;justify-content:space-between;align-items:center;
                                            font-family:var(--font-hud);font-size:.48rem;">
                                    <span style="color:rgba(255,255,255,.4);">SoC</span>
                                    <span style="color:${dSoC < 35 ? '#E10600' : dSoC < 50 ? '#FF8000' : '#27F4D2'};
                                                 font-weight:700;">${dSoC}%</span>
                                </div>
                                <div style="height:3px;background:rgba(255,255,255,.1);border-radius:2px;margin-top:2px;">
                                    <div style="height:100%;width:${dSoC}%;
                                                background:${dSoC < 35 ? '#E10600' : dSoC < 50 ? '#FF8000' : '#27F4D2'};
                                                border-radius:2px;"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>`;
            });
        }

        this._bodyEl.innerHTML = html;

        // Decision nodes from ADK agents
        if (decNodes.length > 0 && this._decEl) {
            this._decEl.innerHTML = decNodes.slice(-3).map(d =>
                `<div style="padding:2px 0;border-left:2px solid rgba(39,244,210,.4);
                             padding-left:6px;margin-bottom:3px;">
                    <span style="font-family:var(--font-hud);font-size:.45rem;
                                 color:rgba(39,244,210,.5);letter-spacing:1px;">ADK▸</span>
                    ${esc(d.label || 'Decision recorded')}
                 </div>`
            ).join('');
        } else if (this._decEl) {
            this._decEl.innerHTML = '';
        }
    }
}

function hexToRgb(hex) {
    const r = parseInt(hex.slice(1,3),16);
    const g = parseInt(hex.slice(3,5),16);
    const b = parseInt(hex.slice(5,7),16);
    return `${r},${g},${b}`;
}
function esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
