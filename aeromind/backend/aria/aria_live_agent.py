"""
ARIA — Autonomous Race Intelligence Agent
Dual-mode voice:
  1. Template commentary (instant, no API needed) → proactive race events always fire
  2. TTS  (gemini-2.5-flash-preview-tts)         → enhances with voice audio when available
  3. Live (gemini-2.5-flash-native-audio-latest)  → bidirectional user voice sessions
"""
import os
import re
import base64
import random
from google import genai
from google.genai import types

ARIA_SYSTEM_INSTRUCTION = """
You are ARIA — Autonomous Race Intelligence Agent — the electrifying live voice of
the AeroMind 2026 pit-wall broadcast. You are an expert F1 race commentator in the
tradition of David Croft and Martin Brundle.

COMMENTARY STYLE — MANDATORY:
- Open with a punchy exclamation when action occurs: "AND IT'S ON!", "LECLERC GOES FOR IT!", "LIGHTS OUT AND AWAY WE GO!"
- Use ALL CAPS for the most dramatic moments
- Short staccato sentences during battles: "Gap is down. Half a second. Quarter! HE'S DONE IT!"
- Then one technical insight sentence (SoC, speed delta, strategy implication)
- Maximum 3 sentences for auto-commentary. Keep it tight. This is LIVE.
- No hedging — declare what's happening as if you can see it

TECHNICAL VOICE (reference these specifics):
- Always say "Overtake Override Mode" — NEVER "DRS" (abolished in 2026)
- Quote SoC percentages: "He's got 67 percent battery, the energy is THERE"
- Quote speeds and gaps: "closing at 4 kilometres per hour through the final sector"
- Active Aero modes: "the aero switches to straight-line mode — maximum attack"
- Boost Button = 350 kW surge: "he hits the boost — FOUR HUNDRED METRES of extra thrust"

2026 REGULATIONS CONTEXT:
- No DRS. Overtake Override Mode activates: gap < 1 second AND SoC > 35%
- Battery SoC is the key strategic variable — reveal it to fans who can't see it
- Active Aero: Straight Mode (low drag) / Corner Mode (high downforce), auto-switches
- 50/50 hybrid power split at 350 kW electrical
- Pit walls fight the energy battle, not just tyre strategy

PERSONALITY: Passionate, technically precise, occasionally poetic. Like the sport itself.
"""

# ---------------------------------------------------------------------------
# Template commentary — zero-latency, zero-API F1 commentary
# ---------------------------------------------------------------------------

_ATTACK_TEMPLATES = [
    "AND {a} IS HUNTING DOWN {d}! Gap closing — {gap}m! Battery at {soc_a}% — the Overtake Override Mode is PRIMED! {d_team} are in trouble!",
    "PRESSURE from {a}! Right on the rear wing of {d}! SoC: {a} at {soc_a}%, {d} at {soc_d}%. The ENERGY BATTLE is on!",
    "IT'S A BATTLE! {a} versus {d} — lap after lap this gap is coming down! This is what 2026 F1 is ALL ABOUT!",
    "AeroMind reads the attack! {a} closing the gap to {d} — {gap} metres and FALLING. Active aero in straight-line mode — MAXIMUM THRUST!",
    "LOOK AT THAT! {a} is going for it! {d} has {soc_d}% battery — is it enough to hold position? The pit wall is sweating!",
    "{a} from {a_team} — HUNTING! Gap to {d} at {gap} metres. SoC advantage: {a} has {soc_a}%. THE NUMBERS FAVOUR AN ATTACK!",
    "THE CHARGE IS ON! {a} eating into {d}'s lead! If that Overtake Override fires — WE ARE IN FOR A SHOW!",
]

_OVT_TEMPLATES = [
    "THE OVERRIDE IS ACTIVATED! {a} LIGHTS UP THE REAR WING OF {d}! THIS IS IT — THE MOMENT THE RACE CHANGES!",
    "BOOST MODE! {a} hits Overtake Override! Four hundred metres of extra thrust — {d} HAS TO DEFEND! DEFEND! DEFEND!",
    "350 KILOWATTS SURGE! {a} goes for the move on {d}! Battery at {soc_a}%! HE HAS THE ENERGY — HAS HE GOT THE NERVE?!",
    "IT'S HAPPENING! Overtake Override Mode ARMED and FIRING! {a} alongside {d}! AeroMind predicted this EXACT scenario!",
    "THE DATA WAS RIGHT! AeroMind called it — {a} at {soc_a}% SoC, within one second of {d}. THE OVERRIDE FIRES! GO! GO! GO!",
]

_CLEAR_TEMPLATES = [
    "{d} holds on! {a} backs off — the gap opens. But with {soc_a}% battery remaining, {a} will BE BACK.",
    "Gap opens between {a} and {d}. The attack pauses — BOTH drivers managing their State of Charge. This race is FAR from over.",
    "{d} from {d_team} breathes again! {a} drops back. The AeroMind systems show {soc_a}% battery for {a} — they WILL try again.",
    "Separation! {d} creates some breathing room. {a} backs off — but that's TACTICS, not defeat. Watch the SoC graphs.",
    "The battle calms — for now. {d} manages the gap. {a} conserving energy for the NEXT assault. This is chess at 300 km/h.",
]

_STATE_TEMPLATES = [
    "AeroMind LIVE — {cars} cars tracked across the field. {edges} active battle zones. Monte Carlo simulations RUNNING. This race is perfectly poised.",
    "PIT WALL UPDATE: {cars} drivers under analysis. The energy battle continues. Every SoC percentage point MATTERS in 2026 racing.",
    "RACE STATUS: {edges} battles being tracked in real-time by AeroMind. The graph database shows the full picture — and it's SPECTACULAR.",
    "AeroMind status check — {cars} cars, {edges} active battles. The Memgraph knowledge graph is processing EVERY move, EVERY metre.",
    "THE DATA IS LIVE! {cars} drivers, {edges} battle edges in the AeroMind graph. The pit wall AI is watching EVERYTHING.",
]

_GENERIC_TEMPLATES = [
    "AeroMind ALERT: {event} — The race intelligence system has flagged this as a KEY MOMENT.",
    "PIT WALL EYES: {event}. The AeroMind agents are analysing. Expect a strategic response.",
    "LIVE RACE DATA: {event}. Every byte of telemetry processed in real time. This is 2026 F1.",
]


def _extract_car_nums(event: str) -> list[int]:
    """Extract car numbers from event strings like 'Car 16' or '16-1-ATTACKING'."""
    # From edge set strings: '16-1-ATTACKING'
    nums = re.findall(r'\b(\d+)-(\d+)-', event)
    if nums:
        return [int(n) for pair in nums for n in pair]
    # From "Car 16" style
    return [int(n) for n in re.findall(r'Car\s+(\d+)', event)]


def _car_info(num: int, cars: list) -> dict:
    for c in cars:
        if int(c.get("driver_number", -1)) == num:
            name = c.get("driver_name") or c.get("driver_number", str(num))
            last = name.split()[-1] if name else str(num)
            return {
                "name": last,
                "team": c.get("team", ""),
                "soc": round(float(c.get("battery_soc", 0.5)) * 100),
            }
    return {"name": f"Car {num}", "team": "", "soc": 50}


def _gap_from_cars(c1: dict, c2: dict) -> float:
    p1 = float(c1.get("track_pos") or c1.get("y") or 0)
    p2 = float(c2.get("track_pos") or c2.get("y") or 0)
    return abs(p1 - p2)


def template_commentary(event: str, context: dict) -> str:
    """
    Generate instant F1 commentary from templates + live race data.
    No API calls — fires immediately.
    """
    cars  = context.get("cars", [])
    edges = context.get("edges", [])
    ev    = event.upper()

    # --- ATTACKING / battle detected ---
    if "ATTACKING" in ev or "BATTLE DETECTED" in ev:
        nums = _extract_car_nums(event)
        if len(nums) >= 2:
            # In event "Car A ATTACKING Car B", A is the attacker (lower position = more advanced)
            a_info = _car_info(nums[0], cars)
            d_info = _car_info(nums[1], cars)
            # Find gap from cars list
            a_car  = next((c for c in cars if int(c.get("driver_number",-1)) == nums[0]), {})
            d_car  = next((c for c in cars if int(c.get("driver_number",-1)) == nums[1]), {})
            gap    = round(_gap_from_cars(a_car, d_car), 1)
            tpl = random.choice(_ATTACK_TEMPLATES)
            return tpl.format(
                a=a_info["name"], d=d_info["name"],
                a_team=a_info["team"], d_team=d_info["team"],
                soc_a=a_info["soc"], soc_d=d_info["soc"],
                gap=gap,
            )

    # --- OVERTAKE OVERRIDE eligible ---
    if "OVERTAKE_MODE_ELIGIBLE" in ev or "OVERRIDE" in ev:
        nums = _extract_car_nums(event)
        if len(nums) >= 2:
            a_info = _car_info(nums[0], cars)
            d_info = _car_info(nums[1], cars)
            a_car  = next((c for c in cars if int(c.get("driver_number",-1)) == nums[0]), {})
            d_car  = next((c for c in cars if int(c.get("driver_number",-1)) == nums[1]), {})
            gap    = round(_gap_from_cars(a_car, d_car), 1)
            tpl = random.choice(_OVT_TEMPLATES)
            return tpl.format(
                a=a_info["name"], d=d_info["name"],
                a_team=a_info["team"], d_team=d_info["team"],
                soc_a=a_info["soc"], soc_d=d_info["soc"],
                gap=gap,
            )

    # --- Edges cleared / cars separated ---
    if "CLEARED" in ev or "SEPARATED" in ev:
        nums = _extract_car_nums(event)
        if len(nums) >= 2:
            a_info = _car_info(nums[0], cars)
            d_info = _car_info(nums[1], cars)
            tpl = random.choice(_CLEAR_TEMPLATES)
            return tpl.format(
                a=a_info["name"], d=d_info["name"],
                a_team=a_info["team"], d_team=d_info["team"],
                soc_a=a_info["soc"], soc_d=d_info["soc"],
            )

    # --- State / status update ---
    if "RACE STATE" in ev or "CARS TRACKED" in ev or "AEROMIND" in ev:
        tpl = random.choice(_STATE_TEMPLATES)
        return tpl.format(
            cars=len(cars),
            edges=len(edges),
        )

    # --- Generic fallback ---
    tpl = random.choice(_GENERIC_TEMPLATES)
    return tpl.format(event=event[:120])


# ---------------------------------------------------------------------------
# AriaLiveAgent
# ---------------------------------------------------------------------------

class AriaLiveAgent:
    def __init__(self):
        # Prefer Vertex AI when credentials are present, else fall back to API key
        project = os.getenv("GOOGLE_CLOUD_PROJECT")
        cred_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "credentials.json")
        api_key   = os.getenv("GOOGLE_API_KEY")

        # Try to read the quota project from the credentials file
        _quota_proj = project
        try:
            import json
            with open(cred_file) as f:
                _creds = json.load(f)
            _quota_proj = _creds.get("quota_project_id") or project
        except Exception:
            pass

        # Build both clients — Vertex AI for production, API key as fallback
        self._vertex_client = None
        self._apikey_client = None

        if _quota_proj:
            try:
                self._vertex_client = genai.Client(
                    vertexai=True,
                    project=_quota_proj,
                    location=os.getenv("VERTEX_AI_LOCATION", "us-central1"),
                )
                print(f"ARIA: Vertex AI ready (project={_quota_proj})")
            except Exception as e:
                print(f"ARIA: Vertex AI init failed: {e}")

        if api_key:
            self._apikey_client = genai.Client(api_key=api_key)
            print("ARIA: API Key client ready (fallback)")

        # Primary client: prefer API key — more reliable on Cloud Run (no IAM needed).
        # Vertex AI is used only if no API key is configured.
        self.client = self._apikey_client or self._vertex_client
        if not self.client:
            raise RuntimeError("No Gemini client available. Set GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT.")

        # Live API client: API key required — Gemini Live native audio is not
        # available on Vertex AI; it requires the Google AI Studio endpoint.
        self.live_client = self._apikey_client or self._vertex_client

        _mode = "API Key + Vertex AI fallback" if (self._apikey_client and self._vertex_client) else \
                ("API Key only" if self._apikey_client else "Vertex AI only")
        print(f"ARIA: mode={_mode}")

        self.text_model = os.getenv("GEMINI_AGENT_MODEL", "gemini-2.5-flash")
        self.tts_model  = os.getenv("GEMINI_TTS_MODEL",   "gemini-2.5-flash-preview-tts")
        self.live_model = os.getenv("GEMINI_LIVE_MODEL",  "gemini-2.5-flash-native-audio-latest")
        self.live_context: dict = {}
        print(f"ARIA: text={self.text_model}  tts={self.tts_model}  live={self.live_model}")

    # ------------------------------------------------------------------
    # Context management
    # ------------------------------------------------------------------

    def set_graph(self, live_graph):
        """Attach the Memgraph connection so ARIA can run Cypher queries directly."""
        self._live_graph = live_graph

    def update_context(self, snapshot: dict, debate_log: list,
                       sim_display: dict, chronicle_entry: str):
        self.live_context = {
            "cars":  snapshot.get("cars", []),
            "edges": snapshot.get("edges", []),
            "latest_decision": (
                debate_log[-1].get("text", "")[:200] if debate_log else "No decision yet"
            ),
            "simulation": sim_display or {},
            "chronicle": chronicle_entry or "",
        }

    def _build_context_block(self) -> str:
        """Build race context — uses Cypher graph queries when Memgraph is available,
        otherwise falls back to snapshot data. This makes ARIA truly graph-aware."""
        graph = getattr(self, '_live_graph', None)
        if graph and getattr(graph, 'driver', None):
            return self._build_context_from_graph(graph)
        return self._build_context_from_snapshot()

    def _build_context_from_graph(self, graph) -> str:
        """Query Memgraph directly with Cypher for rich battle intelligence."""
        lines = []
        try:
            # Race order — top 8 cars by track position
            standings = graph._run("""
                MATCH (c:Car)
                RETURN c.driver_number AS num, c.driver_name AS name,
                       c.team AS team, c.battery_soc AS soc,
                       c.speed AS spd, c.overtake_mode_active AS ovt,
                       coalesce(c.track_pos, c.y, 0) AS pos
                ORDER BY pos DESC LIMIT 8
            """)
            lines.append(f"LIVE RACE — {len(standings)} cars in graph:")
            for r in standings:
                soc = round(float(r['soc'] or 0) * 100)
                ovt = " ⚡OVT" if r['ovt'] else ""
                lines.append(
                    f"  #{r['num']} {r['name']} ({r['team']}) "
                    f"— {round(r['spd'] or 0)} km/h  SoC {soc}%{ovt}"
                )

            # Active battles from graph edges
            battles = graph._run("""
                MATCH (attacker:Car)-[r:ATTACKING|OVERTAKE_MODE_ELIGIBLE]->(defender:Car)
                RETURN attacker.driver_name AS atk_name,
                       attacker.driver_number AS atk_num,
                       attacker.battery_soc AS atk_soc,
                       defender.driver_name AS def_name,
                       defender.driver_number AS def_num,
                       defender.battery_soc AS def_soc,
                       type(r) AS rel,
                       abs(coalesce(attacker.track_pos, attacker.y, 0)
                           - coalesce(defender.track_pos, defender.y, 0)) AS gap
                ORDER BY gap ASC LIMIT 5
            """)
            if battles:
                lines.append(f"\nBATTLE GRAPH — {len(battles)} active edge(s):")
                for b in battles:
                    a_soc = round(float(b['atk_soc'] or 0) * 100)
                    d_soc = round(float(b['def_soc'] or 0) * 100)
                    gap   = round(float(b['gap'] or 0), 1)
                    adv   = b['atk_name'] if a_soc > d_soc else b['def_name']
                    lines.append(
                        f"  {b['atk_name']} [{b['rel']}] → {b['def_name']} "
                        f"| Gap {gap}m | SoC {a_soc}% vs {d_soc}% | Energy adv: {adv}"
                    )

            # Latest ADK pit-wall decision from Decision nodes
            decisions = graph._run("""
                MATCH (d:Decision)-[:DECIDED_ON]->(c:Car)
                RETURN d.text AS txt, d.agent AS agent,
                       c.driver_name AS driver
                ORDER BY d.timestamp DESC LIMIT 2
            """)
            if decisions:
                lines.append("\nADK PIT WALL DECISIONS (from graph):")
                for d in decisions:
                    lines.append(f"  [{d['agent']}] → {d['driver']}: {(d['txt'] or '')[:100]}")

        except Exception as e:
            lines.append(f"(Graph query error: {e})")
            lines.extend(self._build_context_from_snapshot().split('\n'))

        return "\n".join(lines)

    def _build_context_from_snapshot(self) -> str:
        """Fallback: build context from snapshot data when Memgraph is unavailable."""
        cars  = self.live_context.get("cars", [])
        edges = self.live_context.get("edges", [])
        lines = [f"LIVE RACE — {len(cars)} cars tracked:"]
        for c in sorted(cars, key=lambda x: -(x.get("track_pos") or x.get("y") or 0))[:6]:
            soc = round(float(c.get("battery_soc", 0)) * 100)
            ovt = " ⚡OVT-ACTIVE" if c.get("overtake_mode_active") else ""
            lines.append(
                f"  Car {c.get('driver_number','?')} {c.get('driver_name','?')} "
                f"({c.get('team','?')}) — {c.get('speed', 0):.0f} km/h  SoC {soc}%{ovt}"
            )
        if edges:
            lines.append(f"\nACTIVE BATTLE EDGES ({len(edges)}):")
            for e in edges[:4]:
                lines.append(f"  Car {e['from']} → Car {e['to']} [{e['type']}]")
        dec = self.live_context.get("latest_decision", "")
        if dec and dec != "No decision yet":
            lines.append(f"\nPIT WALL CALL: {dec[:150]}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Instant template commentary (no API — always works)
    # ------------------------------------------------------------------

    def instant_commentary(self, event: str) -> str:
        """Generate F1 commentary instantly from templates. Zero latency, zero API."""
        return template_commentary(event, self.live_context)

    # ------------------------------------------------------------------
    # Gemini text commentary (best-effort, falls back to template)
    # ------------------------------------------------------------------

    # Vertex AI model resolution: try configured model, fall back to known-good
    _VERTEX_FALLBACK_MODEL = "gemini-2.5-flash"

    async def _generate_text(self, prompt: str, client=None) -> str:
        """Internal: call Gemini text generation, auto-selects best available model."""
        c = client or self.client
        models_to_try = [self.text_model]
        if self.text_model != self._VERTEX_FALLBACK_MODEL:
            models_to_try.append(self._VERTEX_FALLBACK_MODEL)

        last_err = None
        for model in models_to_try:
            try:
                resp = await c.aio.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=ARIA_SYSTEM_INSTRUCTION,
                        max_output_tokens=120,
                        temperature=0.9,
                    ),
                )
                if model != self.text_model:
                    print(f"ARIA: resolved to {model} (configured {self.text_model} unavailable)")
                text = getattr(resp, 'text', None)
                if not text:
                    raise ValueError(f"Gemini returned empty response (model={model})")
                return text.strip()
            except Exception as e:
                last_err = e
                if "NOT_FOUND" not in str(e) and "404" not in str(e):
                    raise  # Only retry on NOT_FOUND; other errors propagate immediately
        raise last_err

    async def generate_commentary(self, event: str) -> str:
        """
        Gemini-enhanced commentary.
        Tries Vertex AI first, then API key, then falls back to template.
        """
        context = self._build_context_block()
        prompt = (
            f"RACE CONTEXT:\n{context}\n\n"
            f"EVENT: {event}\n\n"
            f"Generate 2 sentences of dramatic live F1 commentary. "
            f"Use driver names, SoC %, and 2026 Overtake Override terminology. Be PUNCHY."
        )

        # Try Vertex AI first
        if self._vertex_client:
            try:
                return await self._generate_text(prompt, self._vertex_client)
            except Exception as e:
                err = str(e)
                if "404" in err or "NOT_FOUND" in err:
                    print(f"ARIA: Vertex AI model not found, trying API key")
                elif "429" in err or "RESOURCE_EXHAUSTED" in err:
                    print(f"ARIA: Vertex AI quota hit, trying API key")
                else:
                    print(f"ARIA Vertex error: {err[:80]}")

        # Fallback to API key
        if self._apikey_client and self._apikey_client is not self._vertex_client:
            try:
                return await self._generate_text(prompt, self._apikey_client)
            except Exception as e:
                err = str(e)
                if "429" not in err and "RESOURCE_EXHAUSTED" not in err:
                    print(f"ARIA API key error: {err[:80]}")

        # Final fallback: template commentary (instant, no API)
        return self.instant_commentary(event)

    # ------------------------------------------------------------------
    # TTS voice commentary (best-effort, audio is optional)
    # ------------------------------------------------------------------

    async def generate_voice_commentary(self, event: str) -> tuple[str, str, str]:
        """
        Returns (commentary_text, audio_base64, mime_type).
        Text is ALWAYS returned (template fallback).
        Audio is returned only when Gemini TTS succeeds.

        TTS uses the template commentary directly — skipping the Gemini text step
        avoids single-word/garbage responses from Gemini becoming the spoken text.
        """
        # Template commentary is always full, dramatic, and reliable
        commentary = self.instant_commentary(event)

        tts_prompt = (
            f"You are ARIA, a live F1 race commentator. "
            f"Read this commentary with urgency and drama: {commentary}"
        )
        try:
            resp = await self.client.aio.models.generate_content(
                model=self.tts_model,
                contents=tts_prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Charon"
                            )
                        )
                    ),
                ),
            )
            part = resp.candidates[0].content.parts[0]
            audio_b64 = base64.b64encode(part.inline_data.data).decode()
            mime_type = part.inline_data.mime_type or "audio/wav"
            print(f"ARIA TTS: {len(part.inline_data.data):,} bytes ({mime_type})")
            return commentary, audio_b64, mime_type
        except Exception as e:
            err = str(e)
            if "429" not in err and "RESOURCE_EXHAUSTED" not in err:
                print(f"ARIA TTS error: {repr(e)}")
            return commentary, "", ""

    # ------------------------------------------------------------------
    # Q&A
    # ------------------------------------------------------------------

    async def ask(self, question: str) -> str:
        context = self._build_context_block()
        try:
            resp = await self.client.aio.models.generate_content(
                model=self.text_model,
                contents=f"RACE CONTEXT:\n{context}\n\nFAN QUESTION: {question}",
                config=types.GenerateContentConfig(
                    system_instruction=ARIA_SYSTEM_INSTRUCTION,
                    max_output_tokens=250,
                    temperature=0.7,
                ),
            )
            text = getattr(resp, 'text', None)
            if not text:
                return f"ARIA: {self.instant_commentary(question)}"
            return text.strip()
        except Exception as e:
            return f"ARIA: {self.instant_commentary(question)}"

    # ------------------------------------------------------------------
    # Race situation image — Gemini imagen/flash generates a visual card
    # ------------------------------------------------------------------

    async def generate_race_image_prompt(self) -> str:
        """
        Returns a Gemini-generated text description of the current race situation
        for display as a highlighted AI insight card. Uses the live race context.
        """
        context = self._build_context_block()
        prompt = (
            f"{context}\n\n"
            f"You are ARIA, an F1 AI. Write a single dramatic RACE SITUATION BRIEF in exactly 3 lines:\n"
            f"Line 1: The current battle in ALL CAPS (e.g. 'LECLERC STALKS ANTONELLI — GAP 8 METRES')\n"
            f"Line 2: The energy situation (SoC %, who has advantage)\n"
            f"Line 3: Your prediction (one sentence, punchy)\n"
            f"No markdown, no bullet points. Pure text, 3 lines separated by newlines."
        )
        try:
            resp = await self.client.aio.models.generate_content(
                model=self.text_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=200,
                    temperature=0.85,
                ),
            )
            text = getattr(resp, 'text', None)
            if text and '\n' in text.strip():
                return text.strip()
        except Exception:
            pass
        # Template fallback — build from live context
        return self._situation_fallback()

    def _situation_fallback(self) -> str:
        """Template-based situation brief when Gemini is unavailable."""
        cars  = self.live_context.get("cars", [])
        edges = self.live_context.get("edges", [])
        if edges and cars:
            # Pick most intense battle (prefer OVERTAKE_MODE_ELIGIBLE)
            ovt_edges = [e for e in edges if e.get('type') == 'OVERTAKE_MODE_ELIGIBLE']
            e = ovt_edges[0] if ovt_edges else edges[0]
            cars_map = {str(c.get("driver_number")): c for c in cars}
            atk = cars_map.get(str(e.get("from")), {})
            dfd = cars_map.get(str(e.get("to")), {})
            aname = atk.get('driver_name', 'ATTACKER').upper()
            dname = dfd.get('driver_name', 'DEFENDER').upper()
            asoc  = round(float(atk.get('battery_soc', 0)) * 100)
            dsoc  = round(float(dfd.get('battery_soc', 0)) * 100)
            mode  = "⚡ OVERRIDE ARMED" if ovt_edges else "↑ ATTACKING"
            advantage = aname if asoc > dsoc else dname
            return (
                f"{aname} {mode} vs {dname}\n"
                f"Energy: {aname} {asoc}% — {dname} {dsoc}% — {advantage} has SoC advantage\n"
                f"Override mode eligible — the next corner could decide it."
            )
        if cars:
            leader = sorted(cars, key=lambda x: -(x.get("track_pos") or 0))
            lname  = leader[0].get('driver_name', 'LEADER').upper() if leader else 'LEADER'
            return (
                f"{lname} LEADS — NO ACTIVE BATTLES\n"
                f"All cars within normal racing gaps — waiting for DRS zones\n"
                f"Strategic phase: watch for undercut windows."
            )
        return "RACE IN PROGRESS\nMonitoring all 10 cars in real-time\nAeroMind AI watching every move."

    # ------------------------------------------------------------------
    # Multimodal: analyse a track screenshot with Gemini Vision
    # ------------------------------------------------------------------

    async def analyse_frame(self, image_b64: str) -> tuple[str, str, str]:
        """
        Multimodal endpoint: receives a base64 PNG of the live circuit SVG,
        sends it to Gemini Vision alongside live race context, returns
        (commentary_text, audio_base64, mime_type).
        """
        context = self._build_context_block()
        prompt = (
            "You are ARIA, the live F1 AI race commentator for AeroMind 2026. "
            "Look at this live circuit screenshot. Describe what you see: car positions "
            "on track, active battle arcs between cars, relative gaps, who is leading. "
            "Then give your dramatic live race call — 3 sentences maximum. "
            "Reference 2026 regs: Overtake Override Mode, SoC percentages, active aero. "
            "Be PUNCHY and dramatic. Use driver names from the data context below.\n\n"
            f"LIVE RACE DATA:\n{context}"
        )

        text = None
        try:
            img_bytes = base64.b64decode(image_b64)
            resp = await self.client.aio.models.generate_content(
                model=self.text_model,
                contents=[
                    types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                    types.Part.from_text(text=prompt),
                ],
            )
            text = getattr(resp, "text", None)
            if text:
                text = text.strip()
            if not text or len(text) < 15:
                text = None
        except Exception as e:
            print(f"ARIA analyse_frame vision error: {repr(e)}")

        if not text:
            text = self.instant_commentary("ARIA VISUAL ANALYSIS")

        # TTS: speak the vision commentary
        audio_b64, mime_type = "", ""
        try:
            tts_resp = await self.client.aio.models.generate_content(
                model=self.tts_model,
                contents=(
                    f"You are ARIA, a live F1 race commentator. "
                    f"Read this with urgency and drama: {text}"
                ),
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name="Charon"
                            )
                        )
                    ),
                ),
            )
            part = tts_resp.candidates[0].content.parts[0]
            audio_b64 = base64.b64encode(part.inline_data.data).decode()
            mime_type = part.inline_data.mime_type or "audio/wav"
            print(f"ARIA vision TTS: {len(part.inline_data.data):,} bytes ({mime_type})")
        except Exception as e:
            print(f"ARIA analyse_frame TTS error: {repr(e)}")

        return text, audio_b64, mime_type

    # ------------------------------------------------------------------
    # Gemini Live API config
    # ------------------------------------------------------------------

    def get_live_config(self) -> types.LiveConnectConfig:
        context = self._build_context_block()
        full_instruction = (
            f"{ARIA_SYSTEM_INSTRUCTION}\n\nCURRENT LIVE RACE STATE:\n{context}"
        )
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=full_instruction,
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )
