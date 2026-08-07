from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import secrets
import sqlite3
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable

from companion_prompt import build_companion_instructions, build_realtime_instructions

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
TEMPLATE_DIR = ROOT / "templates"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()

DB_PATH = Path(os.getenv("DATABASE_PATH", str(ROOT / "data" / "khotso.db"))).expanduser()
APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-this-local-secret").encode("utf-8")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in {"1", "true", "yes", "on"}
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5").strip() or "gpt-5"
OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime").strip() or "gpt-realtime"
OPENAI_TRANSCRIPTION_MODEL = (
    os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe").strip()
    or "gpt-4o-mini-transcribe"
)
OPENAI_TIMEOUT_SECONDS = max(10, int(os.getenv("OPENAI_TIMEOUT_SECONDS", "120")))
MAX_HISTORY_MESSAGES = max(8, min(100, int(os.getenv("MAX_HISTORY_MESSAGES", "36"))))
MAX_BODY_BYTES = 1_500_000
SESSION_TTL_SECONDS = 60 * 60 * 24 * 14

REALTIME_VOICES = ("cedar", "marin", "echo", "ash", "verse", "sage", "coral", "alloy", "ballad", "shimmer")
TURN_EAGERNESS = {"low", "medium", "high", "auto"}
VOICE_LANGUAGES = {"auto", "en", "fr", "es"}

DEFAULT_SETTINGS: dict[str, str] = {
    "user_name": "Rorisang",
    "companion_name": "Khotso",
    "about_user": (
        "Rorisang values faith, family, mutual respect, stability, independence, emotional connection, "
        "practical support, honest communication, and shared growth."
    ),
    "memory_notes": "",
    "style_notes": "Be warm, gently direct, encouraging, calm, and practical.",
    "faith_mode": "true",
    "auto_speak": "true",
    "voice_name": "",
    "voice_rate": "0.95",
    "realtime_voice": "cedar",
    "realtime_speed": "0.95",
    "turn_eagerness": "low",
    "voice_language": "auto",
    "timezone": "America/Edmonton",
}

INITIAL_MESSAGE = (
    "Hello, Rorisang. I’m Khotso—your fictional AI husband companion. I’m here to listen, encourage "
    "you, pray with you when you ask, celebrate your wins, and help you think things through with warmth "
    "and honesty. How is your heart today?"
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger("khotso")


def validate_runtime_config() -> None:
    if SESSION_COOKIE_SECURE and not APP_PASSWORD:
        raise RuntimeError("APP_PASSWORD is required when SESSION_COOKIE_SECURE=true.")
    if SESSION_COOKIE_SECURE and SESSION_SECRET in {b"", b"change-this-local-secret"}:
        raise RuntimeError("Set a long random SESSION_SECRET for an HTTPS deployment.")


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def init_db() -> None:
    with connect_db() as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'typed',
                external_id TEXT UNIQUE,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(messages)")}
        if "source" not in columns:
            connection.execute("ALTER TABLE messages ADD COLUMN source TEXT NOT NULL DEFAULT 'typed'")
        if "external_id" not in columns:
            connection.execute("ALTER TABLE messages ADD COLUMN external_id TEXT")
            connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_external_id ON messages(external_id)")
        connection.executemany(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
            DEFAULT_SETTINGS.items(),
        )
        count = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        if count == 0:
            connection.execute(
                "INSERT INTO messages(role, content, source) VALUES ('assistant', ?, 'system')",
                (INITIAL_MESSAGE,),
            )
        connection.commit()


def get_settings() -> dict[str, str]:
    values = dict(DEFAULT_SETTINGS)
    with connect_db() as connection:
        values.update({row["key"]: row["value"] for row in connection.execute("SELECT key, value FROM settings")})
    return values


def _text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _number(value: Any, default: float, low: float = 0.6, high: float = 1.5) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return f"{max(low, min(high, number)):.2f}"


def update_settings(payload: dict[str, Any]) -> dict[str, str]:
    current = get_settings()
    updates: dict[str, str] = {}
    limits = {
        "user_name": 80,
        "companion_name": 80,
        "about_user": 3000,
        "memory_notes": 3000,
        "style_notes": 2000,
        "voice_name": 180,
        "timezone": 80,
    }
    for key, limit in limits.items():
        if key in payload:
            value = _text(payload[key], limit)
            if key in {"user_name", "companion_name"} and not value:
                value = DEFAULT_SETTINGS[key]
            updates[key] = value
    for key in ("faith_mode", "auto_speak"):
        if key in payload:
            updates[key] = (
                "true"
                if payload[key] is True or str(payload[key]).lower() in {"1", "true", "yes", "on"}
                else "false"
            )
    if "voice_rate" in payload:
        updates["voice_rate"] = _number(payload["voice_rate"], float(current["voice_rate"]))
    if "realtime_speed" in payload:
        updates["realtime_speed"] = _number(payload["realtime_speed"], float(current["realtime_speed"]))
    if "realtime_voice" in payload:
        voice = _text(payload["realtime_voice"], 30).lower()
        updates["realtime_voice"] = voice if voice in REALTIME_VOICES else current["realtime_voice"]
    if "turn_eagerness" in payload:
        eagerness = _text(payload["turn_eagerness"], 12).lower()
        updates["turn_eagerness"] = eagerness if eagerness in TURN_EAGERNESS else current["turn_eagerness"]
    if "voice_language" in payload:
        language = _text(payload["voice_language"], 12).lower()
        updates["voice_language"] = language if language in VOICE_LANGUAGES else current["voice_language"]
    if updates:
        with connect_db() as connection:
            connection.executemany(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                updates.items(),
            )
            connection.commit()
    current.update(updates)
    return current


def list_messages(limit: int = MAX_HISTORY_MESSAGES) -> list[dict[str, Any]]:
    with connect_db() as connection:
        rows = connection.execute(
            "SELECT id, role, content, source, created_at FROM messages ORDER BY id DESC LIMIT ?",
            (max(1, min(200, limit)),),
        ).fetchall()
    return [dict(row) for row in reversed(rows)]


def add_message(role: str, content: str, source: str = "typed", external_id: str | None = None) -> bool:
    if role not in {"user", "assistant"}:
        raise ValueError("Unsupported message role.")
    clean = _text(content, 12_000)
    if not clean:
        return False
    try:
        with connect_db() as connection:
            connection.execute(
                "INSERT INTO messages(role, content, source, external_id) VALUES (?, ?, ?, ?)",
                (role, clean, _text(source, 30) or "typed", _text(external_id, 180) or None),
            )
            connection.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def clear_messages() -> None:
    with connect_db() as connection:
        connection.execute("DELETE FROM messages")
        connection.commit()


def has_api_key(value: str | None = None) -> bool:
    key = (OPENAI_API_KEY if value is None else value).strip()
    return bool(key and key != "sk-your-key-here")


def safety_identifier(settings: dict[str, str]) -> str:
    seed = f"khotso:{settings.get('user_name', 'user')}".encode("utf-8")
    return hashlib.sha256(seed).hexdigest()[:64]


def openai_json_request(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not has_api_key():
        raise RuntimeError("Add OPENAI_API_KEY to the server configuration before sending messages.")
    request = urllib.request.Request(
        f"https://api.openai.com{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=OPENAI_TIMEOUT_SECONDS,
            context=ssl.create_default_context(),
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail).get("error", {}).get("message", detail)
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"OpenAI request failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach OpenAI: {exc.reason}") from exc


def extract_output_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        parts.append(direct.strip())
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                text = content["text"].strip()
                if text:
                    parts.append(text)
    return "\n".join(dict.fromkeys(parts)).strip()


def generate_reply(message: str, settings: dict[str, str], history: list[dict[str, Any]]) -> str:
    inputs = [
        {"role": item["role"], "content": item["content"]}
        for item in history[-MAX_HISTORY_MESSAGES:]
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    inputs.append({"role": "user", "content": message})
    payload = {
        "model": OPENAI_MODEL,
        "instructions": build_companion_instructions(settings),
        "input": inputs,
        "max_output_tokens": 1200,
        "store": False,
        "safety_identifier": safety_identifier(settings),
    }
    text = extract_output_text(openai_json_request("/v1/responses", payload))
    if not text:
        raise RuntimeError("The AI response did not contain any text.")
    return text


def build_realtime_session_config(
    settings: dict[str, str],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    voice = settings.get("realtime_voice", "cedar")
    if voice not in REALTIME_VOICES:
        voice = "cedar"
    eagerness = settings.get("turn_eagerness", "low")
    if eagerness not in TURN_EAGERNESS:
        eagerness = "low"
    transcription: dict[str, Any] = {"model": OPENAI_TRANSCRIPTION_MODEL}
    language = settings.get("voice_language", "auto")
    if language in VOICE_LANGUAGES - {"auto"}:
        transcription["language"] = language
    try:
        speed = max(0.6, min(1.5, float(settings.get("realtime_speed", "0.95"))))
    except ValueError:
        speed = 0.95
    return {
        "type": "realtime",
        "model": OPENAI_REALTIME_MODEL,
        "output_modalities": ["audio"],
        "instructions": build_realtime_instructions(settings, history),
        "max_output_tokens": 900,
        "audio": {
            "input": {
                "transcription": transcription,
                "turn_detection": {
                    "type": "semantic_vad",
                    "eagerness": eagerness,
                    "create_response": True,
                    "interrupt_response": True,
                },
            },
            "output": {"voice": voice, "speed": speed},
        },
    }


def encode_multipart(
    parts: Iterable[tuple[str, str, str]],
    boundary: str | None = None,
) -> tuple[bytes, str]:
    boundary = boundary or f"----khotso-{secrets.token_hex(16)}"
    chunks: list[bytes] = []
    for name, value, content_type in parts:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n'.encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def create_realtime_call(
    offer_sdp: str,
    settings: dict[str, str],
    history: list[dict[str, Any]],
) -> str:
    if not has_api_key():
        raise RuntimeError("Add OPENAI_API_KEY to the server configuration before starting a live call.")
    session = json.dumps(
        build_realtime_session_config(settings, history),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    body, boundary = encode_multipart(
        (
            ("sdp", offer_sdp, "application/sdp"),
            ("session", session, "application/json"),
        )
    )
    request = urllib.request.Request(
        "https://api.openai.com/v1/realtime/calls",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=OPENAI_TIMEOUT_SECONDS,
            context=ssl.create_default_context(),
        ) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(detail).get("error", {}).get("message", detail)
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"OpenAI live-call request failed ({exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach OpenAI for the live call: {exc.reason}") from exc


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def make_session_token() -> str:
    payload = json.dumps(
        {"exp": int(time.time()) + SESSION_TTL_SECONDS, "nonce": secrets.token_hex(8)},
        separators=(",", ":"),
    ).encode()
    encoded = _b64(payload)
    signature = _b64(hmac.new(SESSION_SECRET, encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def valid_session_token(token: str) -> bool:
    try:
        encoded, signature = token.split(".", 1)
        expected = _b64(hmac.new(SESSION_SECRET, encoded.encode(), hashlib.sha256).digest())
        payload = json.loads(_unb64(encoded))
        return hmac.compare_digest(signature, expected) and int(payload["exp"]) > int(time.time())
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False


def parse_cookies(header: str) -> dict[str, str]:
    output: dict[str, str] = {}
    for part in header.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            output[key.strip()] = value.strip()
    return output


def security_headers(cache: str = "no-store") -> dict[str, str]:
    return {
        "Cache-Control": cache,
        "Content-Security-Policy": (
            "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'; "
            "script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
            "media-src 'self' blob:; connect-src 'self' https://api.openai.com wss://api.openai.com"
        ),
        "Cross-Origin-Opener-Policy": "same-origin",
        "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }


class KhotsoHandler(BaseHTTPRequestHandler):
    server_version = "Khotso/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.address_string(), fmt % args)

    def _authenticated(self) -> bool:
        if not APP_PASSWORD:
            return True
        token = parse_cookies(self.headers.get("Cookie", "")).get("khotso_session", "")
        return valid_session_token(token)

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urllib.parse.urlparse(origin)
        return parsed.netloc == self.headers.get("Host")

    def _send(
        self,
        status: int,
        body: bytes = b"",
        content_type: str = "text/plain; charset=utf-8",
        *,
        cache: str = "no-store",
        extra: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for key, value in security_headers(cache).items():
            self.send_header(key, value)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _read(self, limit: int = MAX_BODY_BYTES) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("Invalid Content-Length.") from exc
        if length < 0 or length > limit:
            raise ValueError("Request body is too large.")
        return self.rfile.read(length)

    def _read_json(self) -> dict[str, Any]:
        try:
            payload = json.loads(self._read().decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Request body must be valid JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object.")
        return payload

    def _serve_template(
        self,
        name: str,
        replacements: dict[str, str] | None = None,
    ) -> None:
        text = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
        for key, value in (replacements or {}).items():
            text = text.replace(key, value)
        self._send(200, text.encode("utf-8"), "text/html; charset=utf-8")

    def _require_auth(self) -> bool:
        if self._authenticated():
            return True
        if self.path.startswith("/api/"):
            self._json(401, {"error": "Please sign in to this private companion."})
        else:
            self.send_response(303)
            self.send_header("Location", "/login")
            self.send_header("Content-Length", "0")
            self.end_headers()
        return False

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":
            self._json(200, {"status": "ok"})
            return
        if path == "/login":
            if self._authenticated():
                self._redirect("/")
            else:
                self._serve_template("login.html", {"{{ERROR_BLOCK}}": ""})
            return
        if path == "/service-worker.js":
            self._serve_static("service-worker.js", cache="no-cache")
            return
        if path.startswith("/static/"):
            self._serve_static(path.removeprefix("/static/"), cache="public, max-age=3600")
            return
        if path == "/":
            if self._require_auth():
                self._serve_template("index.html")
            return
        if not self._require_auth():
            return
        if path == "/api/state":
            self._json(
                200,
                {
                    "settings": get_settings(),
                    "messages": list_messages(120),
                    "realtime_available": has_api_key(),
                    "realtime_model": OPENAI_REALTIME_MODEL,
                    "realtime_voices": list(REALTIME_VOICES),
                },
            )
            return
        if path == "/api/export":
            payload = {
                "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "settings": get_settings(),
                "messages": list_messages(200),
            }
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self._send(
                200,
                data,
                "application/json; charset=utf-8",
                extra={"Content-Disposition": "attachment; filename=khotso-conversation.json"},
            )
            return
        self._json(404, {"error": "Not found."})

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if not self._origin_ok():
            self._json(403, {"error": "Cross-origin request blocked."})
            return
        try:
            if path == "/login":
                self._login()
                return
            if path == "/logout":
                self._logout()
                return
            if not self._require_auth():
                return
            if path == "/api/settings":
                self._json(200, {"settings": update_settings(self._read_json())})
            elif path == "/api/chat":
                payload = self._read_json()
                message = _text(payload.get("message"), 5000)
                if not message:
                    self._json(400, {"error": "Enter a message first."})
                    return
                history = list_messages(MAX_HISTORY_MESSAGES)
                settings = get_settings()
                reply = generate_reply(message, settings, history)
                add_message("user", message, "typed")
                add_message("assistant", reply, "typed")
                self._json(200, {"reply": reply})
            elif path == "/api/voice/message":
                payload = self._read_json()
                role = _text(payload.get("role"), 20)
                content = _text(payload.get("content"), 12_000)
                event_id = _text(payload.get("event_id"), 180)
                if role not in {"user", "assistant"} or not content:
                    self._json(400, {"error": "A valid voice transcript is required."})
                    return
                self._json(200, {"saved": add_message(role, content, "voice", event_id)})
            elif path == "/api/clear":
                payload = self._read_json()
                if payload.get("confirm") != "CLEAR":
                    self._json(400, {"error": "Confirmation is required."})
                    return
                clear_messages()
                self._json(200, {"cleared": True})
            elif path == "/api/realtime/session":
                offer = self._read().decode("utf-8", errors="strict").strip()
                if not offer:
                    self._json(400, {"error": "An SDP offer is required."})
                    return
                answer = create_realtime_call(
                    offer,
                    get_settings(),
                    list_messages(MAX_HISTORY_MESSAGES),
                )
                self._send(200, answer.encode("utf-8"), "application/sdp")
            else:
                self._json(404, {"error": "Not found."})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except RuntimeError as exc:
            LOGGER.warning("Request failed: %s", exc)
            self._json(502, {"error": str(exc)})
        except Exception:
            LOGGER.exception("Unhandled request error")
            self._json(500, {"error": "The server could not complete that request."})

    def _redirect(self, location: str, cookie: str | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        for key, value in security_headers().items():
            self.send_header(key, value)
        self.end_headers()

    def _login(self) -> None:
        body = urllib.parse.parse_qs(self._read(20_000).decode("utf-8"))
        password = body.get("password", [""])[0]
        if APP_PASSWORD and not hmac.compare_digest(password, APP_PASSWORD):
            error = '<p class="form-error" role="alert">That password was not accepted.</p>'
            self._serve_template("login.html", {"{{ERROR_BLOCK}}": error})
            return
        flags = ["Path=/", "HttpOnly", "SameSite=Strict", f"Max-Age={SESSION_TTL_SECONDS}"]
        if SESSION_COOKIE_SECURE:
            flags.append("Secure")
        self._redirect("/", f"khotso_session={make_session_token()}; " + "; ".join(flags))

    def _logout(self) -> None:
        flags = "Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
        if SESSION_COOKIE_SECURE:
            flags += "; Secure"
        self._redirect("/login", "khotso_session=; " + flags)

    def _serve_static(self, relative: str, cache: str) -> None:
        safe = Path(relative)
        if safe.is_absolute() or ".." in safe.parts:
            self._json(404, {"error": "Not found."})
            return
        target = (STATIC_DIR / safe).resolve()
        try:
            target.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._json(404, {"error": "Not found."})
            return
        if not target.is_file():
            self._json(404, {"error": "Not found."})
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix in {".js", ".css", ".svg", ".json"}:
            content_type += "; charset=utf-8"
        self._send(200, target.read_bytes(), content_type, cache=cache)


def create_server(host: str = "127.0.0.1", port: int = 5000) -> ThreadingHTTPServer:
    init_db()
    return ThreadingHTTPServer((host, port), KhotsoHandler)


def main() -> None:
    validate_runtime_config()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    server = create_server(host, port)
    LOGGER.info("Khotso is available at http://%s:%s", host, server.server_address[1])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
