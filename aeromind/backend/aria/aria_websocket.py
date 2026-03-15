"""
ARIA WebSocket Bridge — two endpoints:

  /aria        — commentary feed: receives proactive TTS voice commentary + text
                 fans can also send text questions
  /aria/voice  — Gemini Live API bidirectional voice session
                 fan speaks → ARIA hears + responds in voice (interruptible)
"""
import asyncio
import json
import base64
from fastapi import WebSocket, WebSocketDisconnect
from google.genai import types
from backend.aria.aria_live_agent import AriaLiveAgent


class ARIAWebSocketBridge:

    def __init__(self, aria_agent: AriaLiveAgent):
        self.aria = aria_agent
        # Clients connected to the text/commentary feed (/aria)
        self.active_clients: set[WebSocket] = set()
        # Clients that have explicitly clicked ENABLE AUDIO — TTS only for these
        self._audio_clients: set[WebSocket] = set()

    # ------------------------------------------------------------------
    # /aria  — commentary feed + text questions
    # ------------------------------------------------------------------

    async def handle_fan_connection(self, websocket: WebSocket):
        """
        Commentary feed — proactive TTS pushed by broadcast_event().
        Keepalive ping every 20s so the connection doesn't time out when there
        are no race events (e.g. safety car, no battles).
        """
        await websocket.accept()
        self.active_clients.add(websocket)
        print(f"ARIA feed: client connected ({len(self.active_clients)} total)")

        try:
            await websocket.send_json({
                "type": "status",
                "text": "ARIA ONLINE — live F1 2026 race commentary active.",
            })

            # Two concurrent tasks: receive any client messages + send keepalive pings
            async def _keepalive():
                while True:
                    await asyncio.sleep(20)
                    try:
                        await websocket.send_json({"type": "ping"})
                    except Exception:
                        return

            async def _recv():
                while True:
                    try:
                        raw = await websocket.receive_text()
                        msg = json.loads(raw)
                        if msg.get("type") == "question":
                            question = (msg.get("text") or "").strip()
                            if question:
                                await websocket.send_json({"type": "typing"})
                                answer = await self.aria.ask(question)
                                await websocket.send_json({"type": "answer", "text": answer})
                        elif msg.get("type") == "audio_enable":
                            # Client clicked ENABLE AUDIO — opt in to TTS
                            self._audio_clients.add(websocket)
                            print(f"ARIA: client opted into TTS audio ({len(self._audio_clients)} audio clients)")
                        elif msg.get("type") == "audio_disable":
                            self._audio_clients.discard(websocket)
                    except json.JSONDecodeError:
                        continue
                    except Exception:
                        return

            ka_task   = asyncio.create_task(_keepalive())
            recv_task = asyncio.create_task(_recv())
            done, pending = await asyncio.wait(
                [ka_task, recv_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()

        except WebSocketDisconnect:
            pass
        except Exception as e:
            print(f"ARIA feed error: {repr(e)}")
        finally:
            self.active_clients.discard(websocket)
            self._audio_clients.discard(websocket)
            print(f"ARIA feed: client disconnected ({len(self.active_clients)} remaining)")

    async def broadcast_event(self, event_text: str):
        """
        Called by race_loop when a new battle event is detected.

        Two-phase delivery:
          1. INSTANT: template commentary text sent to all clients immediately (no API wait)
          2. ENHANCED: if Gemini TTS succeeds, send audio as a follow-up message
        """
        if not self.active_clients:
            return

        # Phase 1 — instant text (template-based, zero latency)
        instant_text = self.aria.instant_commentary(event_text)
        instant_payload = json.dumps({
            "type":      "commentary",
            "text":      instant_text,
            "audio_b64": "",
            "mime_type": "",
        })
        dead: set[WebSocket] = set()
        for ws in list(self.active_clients):
            try:
                await ws.send_text(instant_payload)
            except Exception:
                dead.add(ws)
        self.active_clients -= dead

        # Phase 2 — Gemini TTS: only called if at least one client has enabled audio.
        # This prevents burning Gemini quota when no one is listening with audio.
        audio_targets = self._audio_clients & self.active_clients
        if audio_targets:
            try:
                commentary, audio_b64, mime_type = await self.aria.generate_voice_commentary(event_text)
                if audio_b64:
                    audio_payload = json.dumps({
                        "type":      "audio_update",
                        "text":      commentary,
                        "audio_b64": audio_b64,
                        "mime_type": mime_type,
                    })
                    dead2: set[WebSocket] = set()
                    for ws in list(audio_targets):
                        try:
                            await ws.send_text(audio_payload)
                        except Exception:
                            dead2.add(ws)
                    self._audio_clients -= dead2
                    self.active_clients -= dead2
            except Exception as e:
                print(f"ARIA broadcast TTS (non-critical): {repr(e)}")

    # ------------------------------------------------------------------
    # /aria/voice  — Gemini Live API bidirectional voice
    # ------------------------------------------------------------------

    async def handle_voice_session(self, websocket: WebSocket):
        """
        Full Gemini Live API voice session.
        Fan speaks → audio bytes → Gemini Live → ARIA speaks back.
        Supports interruption (Gemini Live native feature).
        """
        await websocket.accept()
        print("ARIA Live: voice session starting")

        try:
            async with self.aria.live_client.aio.live.connect(
                model=self.aria.live_model,
                config=self.aria.get_live_config(),
            ) as session:

                await websocket.send_json({
                    "type": "voice_ready",
                    "text": "ARIA LIVE — speak now. You can interrupt at any time.",
                })
                print(f"ARIA Live: Gemini session established (model={self.aria.live_model})")

                # --- Task: receive audio FROM Gemini, send TO browser ---
                async def _receive_from_gemini():
                    async for response in session.receive():
                        sc = response.server_content
                        if sc and sc.model_turn:
                            for part in sc.model_turn.parts:
                                if part.inline_data:
                                    audio_b64 = base64.b64encode(
                                        part.inline_data.data
                                    ).decode()
                                    try:
                                        await websocket.send_json({
                                            "type":      "aria_audio",
                                            "data":      audio_b64,
                                            "mime_type": part.inline_data.mime_type,
                                        })
                                    except Exception:
                                        return

                recv_task = asyncio.create_task(_receive_from_gemini())

                # --- Main loop: receive audio FROM browser, send TO Gemini ---
                try:
                    while True:
                        data = await websocket.receive()
                        if "bytes" in data and data["bytes"]:
                            # Raw PCM audio from browser mic (16kHz, 16-bit, mono)
                            await session.send(
                                types.LiveClientRealtimeInput(
                                    media_chunks=[
                                        types.Blob(
                                            data=data["bytes"],
                                            mime_type="audio/pcm;rate=16000",
                                        )
                                    ]
                                )
                            )
                        elif "text" in data and data["text"]:
                            # Fan typed something while in voice mode
                            msg = json.loads(data["text"])
                            if msg.get("type") == "text_inject":
                                await session.send(
                                    types.LiveClientContent(
                                        turns=[types.Content(
                                            role="user",
                                            parts=[types.Part(text=msg.get("text", ""))],
                                        )],
                                        turn_complete=True,
                                    )
                                )
                except (WebSocketDisconnect, asyncio.CancelledError):
                    pass
                finally:
                    recv_task.cancel()

        except Exception as e:
            print(f"ARIA Live session error: {repr(e)}")
            try:
                await websocket.send_json({
                    "type": "voice_error",
                    "text": f"Live API unavailable: {repr(e)}",
                })
            except Exception:
                pass
