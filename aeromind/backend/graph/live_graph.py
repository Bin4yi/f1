import os
from datetime import datetime


def _short_decision(text: str, max_len: int = 12) -> str:
    """Abbreviate a decision for the graph node label."""
    if not text:
        return "ADK"
    words = text.strip().split()
    label = " ".join(words[:2])
    return label[:max_len] if len(label) > max_len else label

try:
    from neo4j import GraphDatabase
    _neo4j_available = True
except ImportError:
    _neo4j_available = False
    print("WARNING: neo4j driver not available")


class LiveGraph:
    """
    AeroMind 2026 — Memgraph real-time race intelligence graph.

    Node types:
        Car      — live telemetry (position, SoC, speed, team)
        Decision — ADK pit-wall decisions written back after analysis

    Edge types:
        ATTACKING              — gap < 20m
        OVERTAKE_MODE_ELIGIBLE — gap < 12m AND SoC > 35%
        DECIDED_ON             — Decision node → Car node (attacker)
    """

    def __init__(self):
        host = os.getenv("MEMGRAPH_HOST", "localhost")
        port = int(os.getenv("MEMGRAPH_PORT", 7687))
        uri  = f"bolt://{host}:{port}"
        self.driver = None
        if _neo4j_available:
            try:
                self.driver = GraphDatabase.driver(uri, auth=("", ""))
                print(f"LiveGraph: Connected to Memgraph at {uri}")
            except Exception as e:
                print(f"LiveGraph: Failed to connect at {uri}: {e}")

    def _run(self, query: str, **params):
        if not self.driver:
            return []
        try:
            with self.driver.session() as s:
                return list(s.run(query, **params))
        except Exception as e:
            print(f"LiveGraph Cypher error: {e}\nQuery: {query[:120]}")
            return []

    def health_check(self) -> bool:
        try:
            return len(self._run("RETURN 1 AS ok")) > 0
        except Exception:
            return False

    # ── Car nodes ────────────────────────────────────────────────────────

    def seed_demo_cars(self):
        """Seed 10 demo cars with realistic 2026 F1 data."""
        cars = [
            (1,  "Verstappen", "Red Bull",     0.82, 298, 200.0),
            (16, "Leclerc",    "Ferrari",       0.74, 296, 185.0),
            (4,  "Norris",     "McLaren",       0.69, 295, 158.0),
            (44, "Hamilton",   "Ferrari",       0.88, 293, 145.0),
            (63, "Russell",    "Mercedes",      0.76, 292, 118.0),
            (14, "Alonso",     "Aston Martin",  0.61, 290, 106.0),
            (55, "Sainz",      "Williams",      0.70, 289,  80.0),
            (81, "Piastri",    "McLaren",       0.65, 288,  68.0),
            (18, "Stroll",     "Aston Martin",  0.58, 287,  42.0),
            (10, "Gasly",      "Alpine",        0.72, 286,  20.0),
        ]
        for drv, name, team, soc, spd, y in cars:
            self.update_car_node(drv, {
                "driver_name": name, "team": team,
                "battery_soc": soc, "speed": spd,
                "x": 1000, "y": y, "z": 0,
                "overtake_mode_active": False,
            })
        print(f"LiveGraph: seeded {len(cars)} demo cars")

    def update_car_node(self, driver_number: int, data: dict):
        self._run(
            "MERGE (c:Car {driver_number: $drv}) SET c += $props",
            drv=int(driver_number), props=data
        )

    def get_car_state(self, driver_number: int) -> dict | None:
        r = self._run(
            "MATCH (c:Car {driver_number: $drv}) RETURN properties(c) AS p",
            drv=int(driver_number)
        )
        return dict(r[0]["p"]) if r else None

    def get_all_cars(self) -> list[dict]:
        return [dict(r["p"]) for r in self._run("MATCH (c:Car) RETURN properties(c) AS p")]

    # ── Battle edges ─────────────────────────────────────────────────────

    def update_battle_edges(self):
        """
        Recompute ATTACKING and OVERTAKE_MODE_ELIGIBLE edges.

        Key design: only compare POSITION-ADJACENT cars (P1 vs P2, P2 vs P3 …).
        This prevents the GPS-coordinate false-positive problem where two cars on
        different parts of the circuit happen to share a similar Cartesian Y value.

        Uses 'track_pos' (race-distance from leader, set by the streamer) falling
        back to 'y' for demo mode where y IS the track position.
        """
        if not self.driver:
            return

        # Wipe all existing battle edges — recompute from scratch each tick
        self._run("MATCH ()-[r:UNDER_DRS|ATTACKING|OVERTAKE_MODE_ELIGIBLE]->() DELETE r")

        # Sort cars by track position descending → leader first
        cars = sorted(
            self.get_all_cars(),
            key=lambda c: -(float(c.get("track_pos") or c.get("y") or 0))
        )
        if len(cars) < 2:
            return

        # Only compare consecutive pairs in race order
        for i in range(len(cars) - 1):
            ahead  = cars[i]
            behind = cars[i + 1]

            pos_a = float(ahead.get("track_pos")  or ahead.get("y")  or 0)
            pos_b = float(behind.get("track_pos") or behind.get("y") or 0)
            gap   = pos_a - pos_b   # positive = ahead car is further along track

            if gap <= 0:
                continue  # data artefact — positions equal or reversed

            n_ahead  = int(ahead.get("driver_number",  -1))
            n_behind = int(behind.get("driver_number", -1))
            soc_b    = float(behind.get("battery_soc") or 0)

            if gap < 20:
                self._run(
                    "MATCH (b:Car {driver_number: $nb}), (a:Car {driver_number: $na}) "
                    "MERGE (b)-[:ATTACKING]->(a)",
                    nb=n_behind, na=n_ahead,
                )
            if gap < 12 and soc_b > 0.35:
                self._run(
                    "MATCH (b:Car {driver_number: $nb}), (a:Car {driver_number: $na}) "
                    "MERGE (b)-[:OVERTAKE_MODE_ELIGIBLE]->(a)",
                    nb=n_behind, na=n_ahead,
                )

    # ── Decision nodes (ADK writes decisions back to Memgraph) ───────────

    def write_decision_node(self, attacker_number: int, defender_number: int,
                            decision_text: str, agent: str = "StrategistAgent"):
        """
        After ADK pit-wall analysis, write the decision back into Memgraph
        as a Decision node linked to the attacker car.
        This makes Memgraph the single source of truth for ALL AI decisions.
        """
        decision_id = f"dec_{attacker_number}v{defender_number}_{int(datetime.now().timestamp())}"
        # Create/update Decision node
        self._run("""
        MERGE (d:Decision {id: $did})
        SET d.text       = $text,
            d.agent      = $agent,
            d.attacker   = $atk,
            d.defender   = $dfn,
            d.timestamp  = $ts
        """,
        did=decision_id, text=decision_text[:200], agent=agent,
        atk=int(attacker_number), dfn=int(defender_number),
        ts=datetime.now().isoformat()
        )
        # Link Decision → Attacker Car
        self._run("""
        MATCH (d:Decision {id: $did}), (c:Car {driver_number: $atk})
        MERGE (d)-[:DECIDED_ON]->(c)
        """, did=decision_id, atk=int(attacker_number))

        # Prune old decisions (keep only last 5 per battle pair)
        self._run("""
        MATCH (d:Decision)
        WHERE d.attacker = $atk AND d.defender = $dfn
        WITH d ORDER BY d.timestamp DESC SKIP 5
        DETACH DELETE d
        """, atk=int(attacker_number), dfn=int(defender_number))

        print(f"LiveGraph: wrote Decision node {decision_id} for Car {attacker_number} vs {defender_number}")

    def get_recent_decisions(self, limit: int = 5) -> list[dict]:
        """Retrieve the most recent ADK decisions from Memgraph."""
        rows = self._run("""
        MATCH (d:Decision)
        RETURN properties(d) AS p
        ORDER BY d.timestamp DESC
        LIMIT $lim
        """, lim=limit)
        return [dict(r["p"]) for r in rows]

    # ── Full snapshot ─────────────────────────────────────────────────────

    def get_full_snapshot(self) -> dict:
        cars = self.get_all_cars()

        edge_rows = self._run("""
        MATCH (c1:Car)-[r]->(c2:Car)
        RETURN c1.driver_number AS from_drv,
               c2.driver_number AS to_drv,
               type(r) AS rel_type
        """)
        edges = [
            {"from": r["from_drv"], "to": r["to_drv"], "type": r["rel_type"]}
            for r in edge_rows
        ]
        return {"cars": cars, "edges": edges}

    def get_full_graph(self) -> dict:
        """
        Return all nodes and edges for the D3 visualization including Decision nodes.
        This is what the frontend graph panel displays.
        """
        cars = self.get_all_cars()

        # Car nodes
        nodes = []
        for car in cars:
            drv = car.get("driver_number")
            nodes.append({
                "id":          f"car_{drv}",
                "label":       car.get("driver_name", f"CAR {drv}"),
                "team":        car.get("team", "Unknown"),
                "driver_number": drv,
                "battery_soc": round((car.get("battery_soc") or 0) * 100),
                "speed":       round(car.get("speed") or 0),
                "y":           car.get("y", 0),
                "overtake_mode_active": car.get("overtake_mode_active", False),
                "node_type":   "car",
            })

        # Decision nodes
        decisions = self.get_recent_decisions(limit=4)
        for dec in decisions:
            did = dec.get("id", "dec")
            nodes.append({
                "id":        did,
                "label":     _short_decision(dec.get("text", "ADK")),
                "node_type": "decision",
                "agent":     dec.get("agent", "ADK"),
            })

        # Car↔Car edges
        edge_rows = self._run("""
        MATCH (c1:Car)-[r]->(c2:Car)
        RETURN c1.driver_number AS f, c2.driver_number AS t, type(r) AS rt
        """)
        links = [
            {"source": f"car_{r['f']}", "target": f"car_{r['t']}", "type": r["rt"]}
            for r in edge_rows
        ]

        # Decision→Car edges
        dec_rows = self._run("""
        MATCH (d:Decision)-[r:DECIDED_ON]->(c:Car)
        RETURN d.id AS did, c.driver_number AS drv
        """)
        for r in dec_rows:
            links.append({
                "source": r["did"],
                "target": f"car_{r['drv']}",
                "type":   "DECIDED_ON",
            })

        return {"nodes": nodes, "links": links}
