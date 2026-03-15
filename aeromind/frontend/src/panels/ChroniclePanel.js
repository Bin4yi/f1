/**
 * ChroniclePanel.js — F1 bottom ticker bar
 * Displays race events in an F1 broadcast-style scrolling ticker.
 */

export class ChroniclePanel {
    constructor() {
        this._scrollEl  = null;
        this._seenIds   = new Set();
        this._entries   = [];
        this._current   = 0;  // which entry is visible on top row
    }

    render(containerId) {
        document.getElementById(containerId).innerHTML = `
            <div id="chronicle-ticker">
                <div class="ticker-label">RACE EVENTS</div>
                <div class="ticker-scroll" id="ticker-scroll">
                    <div class="ticker-entry" style="color:rgba(255,255,255,.3);font-size:.72rem;">
                        Monitoring race data&hellip;
                    </div>
                </div>
            </div>
        `;
        this._scrollEl = document.getElementById('ticker-scroll');
    }

    addEntry(text, id, imageUrl) {
        if (this._seenIds.has(id)) return;
        this._seenIds.add(id);
        this._entries.push({ text, id });

        if (!this._scrollEl) return;

        // Keep only latest 2 entries visible (ticker style)
        const entry = document.createElement('div');
        entry.className = 'ticker-entry';
        entry.innerHTML = `<span class="event-num">EVENT #${id}</span>${this._esc(text)}`;

        // Clear placeholder
        const placeholder = this._scrollEl.querySelector('[style*="0.3"]');
        if (placeholder) placeholder.remove();

        this._scrollEl.appendChild(entry);

        // Trim to 2 entries
        while (this._scrollEl.children.length > 2) {
            this._scrollEl.removeChild(this._scrollEl.firstChild);
        }
    }

    _esc(s) {
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }
}
