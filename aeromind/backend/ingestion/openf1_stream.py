"""
OpenF1Streamer — Live telemetry ingestion for AeroMind 2026

Session modes:
  demo   → Rich 10-car synthetic 2026 F1 race simulation (multiple simultaneous battles)
  latest → Auto-detects the current/most-recent live OpenF1 session
  <int>  → Specific session key (e.g. 9693 = AUS GP 2025)
"""
import asyncio
import httpx
import os
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# 2026 Australian GP result — actual finishing order used as demo baseline
# (OpenF1 streams real data when available; this activates when API is down)
# Result: Russell(P1) Antonelli(P2) Leclerc(P3) Hamilton(P4) Norris(P5) Verstappen(P6)
# ---------------------------------------------------------------------------
_DEMO_GRID = [
    # drv, name,              team,           base_soc, base_speed, base_y
    ( 63,  "Russell",         "Mercedes",      0.88,    301,  200.0),  # P1
    ( 12,  "Antonelli",       "Mercedes",      0.82,    299,  185.0),  # P2 — battle A
    ( 16,  "Leclerc",         "Ferrari",       0.74,    298,  158.0),  # P3 — battle A/B
    ( 44,  "Hamilton",        "Ferrari",       0.88,    296,  143.0),  # P4 — battle B
    (  4,  "Norris",          "McLaren",       0.69,    295,  118.0),  # P5 — battle B/C
    (  1,  "Verstappen",      "Red Bull",      0.76,    294,  104.0),  # P6 — battle C
    ( 87,  "Bearman",         "Haas",          0.62,    289,   75.0),  # P7
    (  5,  "Bortoleto",       "Audi",          0.58,    287,   60.0),  # P9
    ( 10,  "Gasly",           "Alpine",        0.71,    285,   38.0),  # P10
    ( 23,  "Albon",           "Williams",      0.66,    283,   20.0),  # P12
]


class OpenF1Streamer:
    def __init__(self, session_key: str = None, live_graph=None):
        self.session_key   = session_key or os.getenv("OPENF1_SESSION_KEY", "demo")
        self.base_url      = "https://api.openf1.org/v1"
        self.live_graph    = live_graph
        self.headers       = {"User-Agent": "AeroMind-2026/hackathon"}
        self.demo_mode     = str(self.session_key).lower() == "demo"
        self.demo_step     = 0
        self._demo_seeded  = False
        self._driver_cache: dict[int, dict] = {}
        self._resolved_key: str = self.session_key
        self._session_start: datetime | None = None
        self._replay_cursor: datetime | None = None
        self._replay_step   = timedelta(seconds=8)   # advance 8s per poll (≈12x real-time)
        # 2026 regs = SoC/Overtake Override; pre-2026 = DRS system
        self.is_2026_regs: bool = True   # updated on first session fetch

    # (auto-detection removed — session is set explicitly via UI dropdown or .env)

    # -----------------------------------------------------------------------
    # DEMO: RICH 10-CAR 2026 RACE
    # -----------------------------------------------------------------------

    def _demo_locations(self) -> list[dict]:
        """
        2026 Australian GP simulation — actual finishing order as baseline.
        Result: Russell(P1) Antonelli(P2) Leclerc(P3) Hamilton(P4) Norris(P5) Verstappen(P6)

        Three simultaneous battle pairs:
          Battle A (P2 vs P3): Antonelli vs Leclerc — 30-step cycle
          Battle B (P4 vs P5): Hamilton vs Norris   — 40-step cycle (offset 10)
          Battle C (P5 vs P6): Norris vs Verstappen — 25-step cycle (offset 5)
        """
        s = self.demo_step

        # ── Battle A: Antonelli vs Leclerc (P2/P3) ──
        CYCLE_A = 30
        step_a  = s % CYCLE_A
        if step_a <= 12:
            gap_a = max(4.0, 25.0 - step_a * 1.8)      # Leclerc closing
        elif step_a <= 17:
            gap_a = -6.0 + (step_a - 13) * 1.5          # Leclerc briefly ahead
        else:
            gap_a = max(4.0, 22.0 - (CYCLE_A - step_a) * 2.2)  # Antonelli resets

        soc_12 = round(min(0.99, 0.55 + 0.28 * abs((step_a - 15) / 15.0)), 3)
        soc_16 = round(min(0.99, 0.50 + 0.22 * abs((step_a - 10) / 15.0)), 3)

        # ── Battle B: Hamilton vs Norris (P4/P5) ──
        CYCLE_B = 40
        step_b  = (s + 10) % CYCLE_B
        if step_b <= 16:
            gap_b = max(5.0, 28.0 - step_b * 1.6)
        elif step_b <= 22:
            gap_b = -5.0 + (step_b - 17) * 1.0
        else:
            gap_b = max(5.0, 24.0 - (CYCLE_B - step_b) * 2.0)

        soc_44 = round(min(0.99, 0.60 + 0.25 * abs((step_b - 12) / 20.0)), 3)
        soc_4  = round(min(0.99, 0.48 + 0.20 * abs((step_b - 20) / 20.0)), 3)

        # ── Battle C: Norris vs Verstappen (P5/P6) ──
        CYCLE_C = 25
        step_c  = (s + 5) % CYCLE_C
        if step_c <= 10:
            gap_c = max(3.0, 18.0 - step_c * 1.5)
        elif step_c <= 14:
            gap_c = -4.0 + (step_c - 11) * 1.2
        else:
            gap_c = max(3.0, 20.0 - (CYCLE_C - step_c) * 2.5)

        soc_1  = round(min(0.99, 0.52 + 0.24 * abs((step_c - 12) / 12.0)), 3)

        # Russell leads comfortably — stable SoC
        drain  = self.demo_step * 0.0008
        soc_63 = round(min(0.99, max(0.70, 0.88 - drain * 0.5)), 3)

        # Field cars SoC drain
        soc_87 = round(max(0.30, 0.62 - drain), 3)
        soc_5  = round(max(0.25, 0.58 - drain), 3)
        soc_10 = round(max(0.35, 0.71 - drain), 3)
        soc_23 = round(max(0.28, 0.66 - drain), 3)

        # Base positions (y = track metres — P1 at 200, spacing reflects gaps)
        y63  = 200.0                                # P1 Russell — clear lead
        y12  = y63  - 15.0 - gap_a                 # P2 Antonelli
        y16  = y12  - gap_a                         # P3 Leclerc
        y44  = y16  - abs(gap_a) - 20.0            # P4 Hamilton
        y4   = y44  - gap_b                         # P5 Norris
        y1   = y4   - gap_c                         # P6 Verstappen
        y87  = y1   - 28.0                          # P7 Bearman (lapped)
        y5   = y87  - 18.0                          # P9 Bortoleto
        y10  = y5   - 20.0                          # P10 Gasly
        y23  = y10  - 22.0                          # P12 Albon

        def ovt(gap, soc):
            return bool(0 < gap < 12 and soc > 0.35)

        return [
            {"driver_number": 63, "driver_name": "Russell",    "team": "Mercedes",
             "x": 1000, "y": y63, "z": 0, "battery_soc": soc_63, "speed": 301,
             "overtake_mode_active": False},
            {"driver_number": 12, "driver_name": "Antonelli",  "team": "Mercedes",
             "x": 1000, "y": y12, "z": 0, "battery_soc": soc_12, "speed": 299,
             "overtake_mode_active": False},
            {"driver_number": 16, "driver_name": "Leclerc",    "team": "Ferrari",
             "x": 1000, "y": y16, "z": 0, "battery_soc": soc_16, "speed": 298,
             "overtake_mode_active": ovt(gap_a, soc_16)},
            {"driver_number": 44, "driver_name": "Hamilton",   "team": "Ferrari",
             "x": 1000, "y": y44, "z": 0, "battery_soc": soc_44, "speed": 296,
             "overtake_mode_active": False},
            {"driver_number":  4, "driver_name": "Norris",     "team": "McLaren",
             "x": 1000, "y": y4,  "z": 0, "battery_soc": soc_4,  "speed": 295,
             "overtake_mode_active": ovt(gap_b, soc_4)},
            {"driver_number":  1, "driver_name": "Verstappen", "team": "Red Bull",
             "x": 1000, "y": y1,  "z": 0, "battery_soc": soc_1,  "speed": 294,
             "overtake_mode_active": ovt(gap_c, soc_1)},
            {"driver_number": 87, "driver_name": "Bearman",    "team": "Haas",
             "x": 1000, "y": y87, "z": 0, "battery_soc": soc_87, "speed": 289,
             "overtake_mode_active": False},
            {"driver_number":  5, "driver_name": "Bortoleto",  "team": "Audi",
             "x": 1000, "y": y5,  "z": 0, "battery_soc": soc_5,  "speed": 287,
             "overtake_mode_active": False},
            {"driver_number": 10, "driver_name": "Gasly",      "team": "Alpine",
             "x": 1000, "y": y10, "z": 0, "battery_soc": soc_10, "speed": 285,
             "overtake_mode_active": False},
            {"driver_number": 23, "driver_name": "Albon",      "team": "Williams",
             "x": 1000, "y": y23, "z": 0, "battery_soc": soc_23, "speed": 283,
             "overtake_mode_active": False},
        ]

    def _seed_demo_cars(self):
        if not self.live_graph or self._demo_seeded:
            return
        for loc in self._demo_locations():
            drv = loc["driver_number"]
            self.live_graph.update_car_node(drv, {k: v for k, v in loc.items() if k != "driver_number"})
        self._demo_seeded = True
        print(f"OpenF1: seeded {len(_DEMO_GRID)} demo cars")

    # -----------------------------------------------------------------------
    # REAL API HELPERS
    # -----------------------------------------------------------------------

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> list[dict]:
        try:
            r = await client.get(url, timeout=12.0)
            if r.status_code == 404:
                return []
            if r.status_code == 401:
                # OpenF1 locks ALL access during a live race unless authenticated
                body = r.text[:120] if r.text else ""
                if not getattr(self, '_401_logged', False):
                    print(f"OpenF1 401: access locked (live race in progress or API key required). "
                          f"Reverting to demo mode.  Detail: {body}")
                    self._401_logged = True
                self._api_blocked = True
                return []
            self._401_logged = False
            self._api_blocked = False
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError:
            return []
        except Exception as e:
            print(f"OpenF1 fetch error: {e}  ({url[:80]})")
            return []

    async def _refresh_driver_cache(self, client: httpx.AsyncClient):
        url  = f"{self.base_url}/drivers?session_key={self._resolved_key}"
        data = await self._fetch(client, url)
        for d in data:
            num = d.get("driver_number")
            if num is not None:
                self._driver_cache[int(num)] = {
                    "driver_name": d.get("full_name") or d.get("last_name", f"CAR {num}"),
                    "team":        d.get("team_name", "Unknown"),
                    "team_colour": d.get("team_colour", "AAAAAA"),
                }
        print(f"OpenF1: cached {len(self._driver_cache)} drivers for session {self._resolved_key}")

    async def _fetch_session_start(self, client: httpx.AsyncClient) -> datetime | None:
        """Fetch the session start time and detect regulations year."""
        data = await self._fetch(client, f"{self.base_url}/sessions?session_key={self._resolved_key}")
        if data:
            session = data[0]
            year = int(session.get("year", 2026))
            self.is_2026_regs = (year >= 2026)
            # Resolve 'latest' to real session key so other endpoints work
            real_key = session.get("session_key")
            if real_key and str(self._resolved_key).lower() == "latest":
                self._resolved_key = str(real_key)
                print(f"OpenF1: 'latest' resolved to session_key={real_key} "
                      f"({session.get('circuit_short_name','?')} {year})")
            circuit = session.get("circuit_short_name", "?")
            regs_label = "2026 regs (SoC)" if self.is_2026_regs else f"{year} regs (DRS)"
            print(f"OpenF1: session={self._resolved_key} circuit={circuit} "
                  f"year={year} → {regs_label}")
            ds = session.get("date_start", "")
            if ds:
                try:
                    dt = datetime.fromisoformat(ds.replace("Z", "+00:00"))
                    return dt.astimezone(timezone.utc).replace(tzinfo=None)
                except Exception:
                    pass
        return None

    def _date_window(self) -> tuple[str, str]:
        """
        Return (date_from, date_to) for the current query window.
        - Live session (no replay cursor): last 8s from now
        - Historical replay: sliding cursor through the race
        """
        now_utc = datetime.utcnow()

        if self._replay_cursor is None:
            # Live mode: always query last 8 seconds
            d_from = (now_utc - timedelta(seconds=8)).strftime("%Y-%m-%dT%H:%M:%S")
            d_to   = now_utc.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            # Historical replay: 8-second window at current cursor
            d_from = self._replay_cursor.strftime("%Y-%m-%dT%H:%M:%S")
            d_to   = (self._replay_cursor + timedelta(seconds=8)).strftime("%Y-%m-%dT%H:%M:%S")
            # Advance cursor for next poll
            self._replay_cursor += self._replay_step

        return d_from, d_to

    async def fetch_locations(self) -> list[dict]:
        if self.demo_mode:
            return self._demo_locations()

        async with httpx.AsyncClient(headers=self.headers, timeout=12.0) as client:
            if not self._driver_cache:
                await self._refresh_driver_cache(client)

            # Fetch session start for historical replay on first call
            if self._session_start is None:
                self._session_start = await self._fetch_session_start(client)
                if self._session_start:
                    # Skip formation lap: start 10 min into the session
                    self._replay_cursor = self._session_start + timedelta(minutes=10)
                    print(f"OpenF1: replay starting at {self._replay_cursor.isoformat()}")

            d_from, d_to = self._date_window()
            sk = self._resolved_key

            cars = await self._fetch(client,
                f"{self.base_url}/car_data?session_key={sk}&date>={d_from}&date<={d_to}")
            locs = await self._fetch(client,
                f"{self.base_url}/location?session_key={sk}&date>={d_from}&date<={d_to}")

        # Latest record per driver
        latest_car: dict[int, dict] = {}
        for c in cars:
            n = c.get("driver_number")
            if n is not None:
                latest_car[int(n)] = c

        latest_loc: dict[int, dict] = {}
        for lc in locs:
            n = lc.get("driver_number")
            if n is not None:
                latest_loc[int(n)] = lc

        # Build merged records — car_data is primary (always present), loc optional
        all_drivers = set(latest_car.keys()) | set(latest_loc.keys())
        merged = []
        for drv in all_drivers:
            car  = latest_car.get(drv, {})
            loc  = latest_loc.get(drv, {})
            meta = self._driver_cache.get(drv, {})
            spd  = car.get("speed", 0)
            rpm  = car.get("rpm", 10000)
            drs_raw = car.get("drs")

            if self.is_2026_regs:
                # 2026+: no DRS — synthesise SoC from RPM/throttle
                throttle = car.get("throttle", 50)
                soc = round(min(0.99, max(0.15,
                    0.45 + (rpm - 9000) / 50000 + throttle / 1000)), 3)
                drs_open = False
            else:
                # Pre-2026: real DRS — 10/12/14 = open, others = closed
                # Encode DRS as battery_soc for the bar widget (OPEN=0.85, CLOSED=0.15)
                try:
                    drs_val  = int(drs_raw) if drs_raw is not None else 0
                    drs_open = drs_val >= 10
                except (ValueError, TypeError):
                    drs_open = False
                soc = 0.85 if drs_open else 0.15

            merged.append({
                "driver_number": drv,
                "x": loc.get("x", 0),
                "y": loc.get("y", 0),
                "z": loc.get("z", 0),
                "speed": round(spd, 1),
                "battery_soc": soc,
                "drs_open": drs_open,
                "driver_name": meta.get("driver_name", f"CAR {drv}"),
                "team":        meta.get("team", "Unknown"),
                "overtake_mode_active": False,
            })
        return merged

    async def fetch_intervals(self) -> list[dict]:
        if self.demo_mode:
            return []
        d_from, d_to = self._date_window()
        async with httpx.AsyncClient(headers=self.headers, timeout=12.0) as client:
            data = await self._fetch(client,
                f"{self.base_url}/intervals?session_key={self._resolved_key}"
                f"&date>={d_from}&date<={d_to}")
        latest: dict[int, dict] = {}
        for g in data:
            n = g.get("driver_number")
            if n is not None:
                latest[int(n)] = g
        return list(latest.values())

    # -----------------------------------------------------------------------
    # MAIN LOOP
    # -----------------------------------------------------------------------

    async def run(self):
        print(f"OpenF1 Streamer: session='{self.session_key}' demo={self.demo_mode}")

        # Clear stale car nodes from previous run so we start with a clean graph
        if self.live_graph:
            try:
                self.live_graph._run("MATCH (c:Car) DETACH DELETE c")
                print("OpenF1: cleared stale car nodes from Memgraph")
            except Exception:
                pass

        # Seed demo cars or start real-session polling
        if self.demo_mode:
            self._seed_demo_cars()
        else:
            print(f"OpenF1: starting real session replay for key={self._resolved_key}")

        poll_n = 0
        self._api_blocked = False
        self._401_logged  = False
        try:
            while True:
                # If OpenF1 blocked all endpoints (401 — live race in progress),
                # revert to demo mode so the simulation keeps running
                if not self.demo_mode and getattr(self, '_api_blocked', False):
                    print("OpenF1: API locked — reverting to demo mode automatically")
                    self.demo_mode = True
                    self._demo_seeded = False
                    self._api_blocked = False
                    if self.live_graph:
                        try:
                            self.live_graph._run("MATCH (c:Car) DETACH DELETE c")
                        except Exception:
                            pass
                    self._seed_demo_cars()

                if self.live_graph:
                    locations = await self.fetch_locations()

                    for loc in locations:
                        drv = loc.get("driver_number")
                        if drv is None:
                            continue
                        props = {k: v for k, v in loc.items() if k != "driver_number"}
                        # In demo mode y IS the track position — copy it to track_pos
                        # so update_battle_edges() uses the correct race-gap metric
                        if self.demo_mode:
                            props["track_pos"] = props.get("y", 0)
                        self.live_graph.update_car_node(int(drv), props)

                    # Real mode: derive track_pos from gap_to_leader (timing, not GPS)
                    # gap_to_leader (seconds) × avg speed (45 m/s) → metres behind leader
                    if not self.demo_mode:
                        intervals = await self.fetch_intervals()
                        REFERENCE = 10_000.0   # leader's track_pos reference value
                        SPEED_MPS = 45.0       # ~162 km/h average lap speed
                        for iv in intervals:
                            drv   = iv.get("driver_number")
                            gap_s = iv.get("gap_to_leader") or iv.get("interval")
                            if drv is None:
                                continue
                            if gap_s is None:
                                # This driver IS the leader
                                self.live_graph.update_car_node(int(drv), {"track_pos": REFERENCE})
                            else:
                                try:
                                    track_pos = max(0.0, REFERENCE - float(gap_s) * SPEED_MPS)
                                    self.live_graph.update_car_node(int(drv), {"track_pos": track_pos})
                                except (ValueError, TypeError):
                                    pass

                    self.live_graph.update_battle_edges()

                poll_n         += 1
                self.demo_step += 2   # 2x speed — each poll advances 2 simulation steps
                await asyncio.sleep(1.5)

        except asyncio.CancelledError:
            print("Streamer cancelled")
        except Exception as e:
            print(f"Streamer error: {e}")
            import traceback; traceback.print_exc()
