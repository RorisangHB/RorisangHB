from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

_TEST_DIR = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = str(Path(_TEST_DIR.name) / "test.db")
os.environ["APP_PASSWORD"] = ""
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["OPENAI_MODEL"] = "gpt-5"
os.environ["OPENAI_REALTIME_MODEL"] = "gpt-realtime"
os.environ["OPENAI_TRANSCRIPTION_MODEL"] = "gpt-4o-mini-transcribe"

import app  # noqa: E402


class KhotsoAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = app.create_server("127.0.0.1", 0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        _TEST_DIR.cleanup()

    def request_json(self, path: str, payload: dict | None = None) -> tuple[int, dict]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method="POST" if payload is not None else "GET",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def request_sdp(self, offer: str) -> tuple[int, str, str]:
        request = urllib.request.Request(
            self.base + "/api/realtime/session",
            data=offer.encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/sdp"},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return (
                    response.status,
                    response.read().decode("utf-8"),
                    response.headers.get("Content-Type", ""),
                )
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8"), exc.headers.get("Content-Type", "")

    def test_home_page_and_security_headers(self) -> None:
        head_request = urllib.request.Request(self.base + "/", method="HEAD")
        with urllib.request.urlopen(head_request, timeout=5) as head_response:
            self.assertEqual(head_response.status, 200)
            self.assertEqual(head_response.read(), b"")

        request = urllib.request.Request(self.base + "/", method="GET")
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn('id="callButton"', body)
            self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
            self.assertIn("microphone=(self)", response.headers.get("Permissions-Policy", ""))
            self.assertIn("default-src 'self'", response.headers.get("Content-Security-Policy", ""))
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_voice_interface_classes_are_styled(self) -> None:
        css = (app.STATIC_DIR / "styles.css").read_text(encoding="utf-8")
        for class_name in (
            "voice-card",
            "call-readiness",
            "conversation-panel",
            "composer-help",
            "call-stage",
            "call-presence",
            "live-captions",
            "round-control",
        ):
            self.assertIn(f".{class_name}", css)

        self.assertNotIn("var(--wine-100)", css)

    def test_chat_saves_exchange(self) -> None:
        with mock.patch.object(app, "generate_reply", return_value="I hear you, my love."):
            status, data = self.request_json("/api/chat", {"message": "Today was difficult."})
        self.assertEqual(status, 200)
        self.assertEqual(data["reply"], "I hear you, my love.")

        _, state = self.request_json("/api/state")
        contents = [item["content"] for item in state["messages"]]
        self.assertIn("Today was difficult.", contents)
        self.assertIn("I hear you, my love.", contents)

    def test_clear_requires_confirmation(self) -> None:
        status, data = self.request_json("/api/clear", {})
        self.assertEqual(status, 400)
        self.assertIn("Confirmation", data["error"])

    def test_extract_output_text(self) -> None:
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "Hello"},
                        {"type": "output_text", "text": "Rorisang"},
                    ],
                }
            ]
        }
        self.assertEqual(app.extract_output_text(payload), "Hello\nRorisang")

    def test_multipart_contains_sdp_and_session(self) -> None:
        body, boundary = app.encode_multipart(
            (
                ("sdp", "v=0\r\n", "application/sdp"),
                ("session", '{"type":"realtime"}', "application/json"),
            ),
            boundary="unit-test-boundary",
        )
        decoded = body.decode("utf-8")
        self.assertEqual(boundary, "unit-test-boundary")
        self.assertIn('name="sdp"', decoded)
        self.assertIn("v=0", decoded)
        self.assertIn('name="session"', decoded)
        self.assertTrue(decoded.endswith("--unit-test-boundary--\r\n"))

    def test_old_typed_chat_database_migrates(self) -> None:
        old_path = Path(_TEST_DIR.name) / "old-schema.db"
        import sqlite3

        with sqlite3.connect(old_path) as connection:
            connection.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute(
                """
                CREATE TABLE messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            connection.execute(
                "INSERT INTO messages(role, content) VALUES ('assistant', 'Existing conversation')"
            )
            connection.commit()

        original_path = app.DB_PATH
        try:
            app.DB_PATH = old_path
            app.init_db()
            with sqlite3.connect(old_path) as connection:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
                saved = connection.execute(
                    "SELECT content FROM messages WHERE content = 'Existing conversation'"
                ).fetchone()
            self.assertIn("source", columns)
            self.assertIn("external_id", columns)
            self.assertIsNotNone(saved)
        finally:
            app.DB_PATH = original_path

    def test_realtime_session_config_has_voice_and_interruptions(self) -> None:
        settings = dict(app.DEFAULT_SETTINGS)
        settings.update(
            {
                "realtime_voice": "cedar",
                "voice_rate": "1.10",
                "realtime_speed": "1.10",
                "turn_eagerness": "high",
                "voice_language": "en",
            }
        )
        config = app.build_realtime_session_config(
            settings,
            [{"role": "user", "content": "Please remember our last conversation."}],
        )
        self.assertEqual(config["type"], "realtime")
        self.assertEqual(config["model"], "gpt-realtime")
        self.assertEqual(config["audio"]["output"]["voice"], "cedar")
        self.assertEqual(config["audio"]["output"]["speed"], 1.1)
        self.assertEqual(
            config["audio"]["input"]["transcription"]["model"],
            "gpt-4o-mini-transcribe",
        )
        self.assertEqual(
            config["audio"]["input"]["transcription"]["language"],
            "en",
        )
        turn = config["audio"]["input"]["turn_detection"]
        self.assertTrue(turn["interrupt_response"])
        self.assertTrue(turn["create_response"])
        self.assertEqual(turn["eagerness"], "high")
        self.assertIn("AI-generated voice", config["instructions"])
        self.assertIn("Please remember our last conversation.", config["instructions"])
        self.assertNotIn("reasoning", config)

    def test_typed_response_uses_current_model_and_disables_storage(self) -> None:
        settings = dict(app.DEFAULT_SETTINGS)
        with mock.patch.object(
            app,
            "openai_json_request",
            return_value={
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "I am here."}],
                    }
                ]
            },
        ) as mocked:
            reply = app.generate_reply("Hello", settings, [])
        self.assertEqual(reply, "I am here.")
        payload = mocked.call_args.args[1]
        self.assertEqual(payload["model"], "gpt-5")
        self.assertIs(payload["store"], False)

    def test_realtime_sdp_endpoint_proxies_answer(self) -> None:
        with mock.patch.object(app, "create_realtime_call", return_value="v=0\r\no=answer\r\n") as mocked:
            status, body, content_type = self.request_sdp("v=0\r\no=offer\r\n")
        self.assertEqual(status, 200)
        self.assertIn("v=0", body)
        self.assertIn("application/sdp", content_type)
        mocked.assert_called_once()

    def test_state_and_settings(self) -> None:
        status, state = self.request_json("/api/state")
        self.assertEqual(status, 200)
        self.assertEqual(state["settings"]["companion_name"], "Khotso")
        self.assertTrue(state["messages"])
        self.assertTrue(state["realtime_available"])
        self.assertEqual(state["realtime_model"], "gpt-realtime")
        self.assertIn("cedar", state["realtime_voices"])

        status, data = self.request_json(
            "/api/settings",
            {
                "companion_name": "Neo",
                "faith_mode": False,
                "voice_rate": 9,
                "realtime_speed": 9,
                "realtime_voice": "marin",
                "turn_eagerness": "low",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["settings"]["companion_name"], "Neo")
        self.assertEqual(data["settings"]["faith_mode"], "false")
        self.assertEqual(data["settings"]["voice_rate"], "1.50")
        self.assertEqual(data["settings"]["realtime_speed"], "1.50")
        self.assertEqual(data["settings"]["realtime_voice"], "marin")
        self.assertEqual(data["settings"]["turn_eagerness"], "low")

    def test_secure_deployment_requires_password(self) -> None:
        original_secure = app.SESSION_COOKIE_SECURE
        original_password = app.APP_PASSWORD
        original_secret = app.SESSION_SECRET
        try:
            app.SESSION_COOKIE_SECURE = True
            app.APP_PASSWORD = ""
            with self.assertRaisesRegex(RuntimeError, "APP_PASSWORD is required"):
                app.validate_runtime_config()
            app.APP_PASSWORD = "private-password"
            app.SESSION_SECRET = b"unit-test-session-secret-that-is-long"
            app.validate_runtime_config()
        finally:
            app.SESSION_COOKIE_SECURE = original_secure
            app.APP_PASSWORD = original_password
            app.SESSION_SECRET = original_secret

    def test_voice_transcript_is_saved_once(self) -> None:
        payload = {
            "role": "user",
            "content": "This came from my voice call.",
            "event_id": "voice-test-event-1",
        }
        status, first = self.request_json("/api/voice/message", payload)
        self.assertEqual(status, 200)
        self.assertTrue(first["saved"])

        status, second = self.request_json("/api/voice/message", payload)
        self.assertEqual(status, 200)
        self.assertFalse(second["saved"])

        _, state = self.request_json("/api/state")
        matches = [
            item for item in state["messages"]
            if item["content"] == "This came from my voice call."
        ]
        self.assertEqual(len(matches), 1)


if __name__ == "__main__":
    unittest.main()
