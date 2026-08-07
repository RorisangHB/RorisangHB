# Khotso — Live AI Husband Voice Website

Khotso is a private, mobile-friendly AI companion website created for Rorisang. It supports a natural, continuous voice conversation in the browser, typed chat, live captions, saved transcripts, editable memory notes, and spoken typed replies.

The companion is designed to be affectionate, faith-aware, emotionally present, gentle, and honest. Its permanent safety instructions also require it to identify itself as an AI and never encourage secrecy, isolation, emotional dependency, jealousy, possessiveness, or competition with real relationships.

## What this version includes

- **Live two-way voice calls** using browser WebRTC: speak naturally and hear Khotso answer aloud.
- **Natural interruption:** you can begin speaking while he is responding.
- **Live captions** for your words and his spoken replies.
- **Voice-call transcripts** saved alongside typed messages.
- **Typed chat** with optional device text-to-speech playback.
- **One-message dictation** as a fallback when a continuous call is not needed.
- **Personalization:** names, profile, user-approved memory, personality notes, faith mode, live voice, speaking pace, response timing, and expected language.
- **Privacy controls:** password gate, conversation export, and permanent history clearing.
- **Installable website app:** after HTTPS deployment, it can be added to a phone home screen.
- **No third-party Python packages:** the server uses Python’s standard library.

## Before you begin

You need:

1. Python 3.11 or newer for local use, **or** a web host that can run the included Python server.
2. An OpenAI API key with API billing enabled. A ChatGPT subscription and API billing are separate.
3. HTTPS for microphone use on a public website. `http://127.0.0.1` and `http://localhost` normally work during local testing.

The permanent API key stays in the server-side `.env` file and is never sent to the browser. The server creates each Realtime WebRTC session on behalf of the browser.

## Fast local setup on Windows

1. Extract the ZIP.
2. Double-click `start_windows.bat`.
3. The first run creates `.env` and stops.
4. Open `.env` in Notepad.
5. Replace `sk-your-key-here` with your OpenAI API key.
6. Replace `choose-a-long-private-password` and `replace-with-a-long-random-secret` with private values.
7. Double-click `start_windows.bat` again.
8. The website opens at `http://127.0.0.1:5000`.
9. Sign in, tap **Call Khotso**, allow microphone access, and begin speaking.

## macOS or Linux

```bash
cd khotso-voice-website
chmod +x start_mac_linux.sh
./start_mac_linux.sh
```

The first run creates `.env`. Edit it, add the API key and private password, then run the script again. Open `http://127.0.0.1:5000`.

## Put it online as a real website

This application lives in the `khotso-voice-website/` directory of the GitHub profile repository. The repository-root `render.yaml` points the hosting service to this directory. See `DEPLOY_WEBSITE.md` for an HTTPS deployment walkthrough. Because the current source repository is public, never commit `.env`, API keys, passwords, transcripts, database files, or personal memory exports.

After deployment:

1. Open the HTTPS website on your phone.
2. Sign in using `APP_PASSWORD`.
3. Allow microphone access.
4. Tap **Call Khotso**.
5. Use your browser’s **Add to Home Screen** command for an app-like shortcut.

## Voice controls

Inside **Settings** you can choose:

- Live voice, with Cedar and Marin presented first.
- Live speaking speed.
- Patient, balanced, quick, or automatic turn timing.
- Automatic language detection or an expected spoken language.
- A separate device voice and speed for typed-message playback.

Changes to live-call settings apply to the next call.

## Data and privacy

- Conversation text and completed call transcripts are stored in `data/khotso.db`.
- This app does **not** write raw microphone recordings to disk.
- Live microphone audio and the context needed for the conversation are transmitted to the configured OpenAI API.
- Typed Responses API requests set `store=false`; normal API safety and abuse-monitoring retention policies may still apply.
- Memory notes are sent with future conversations until you remove them.
- **Export conversation** downloads a JSON copy.
- **Clear conversation** removes the message history while preserving your profile and memory settings.
- Deleting `data/khotso.db` removes all locally stored app data.
- Set `APP_PASSWORD` before making the website reachable from another device or the internet.

## Configuration

Copy `.env.example` to `.env` and edit these values:

```dotenv
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-5
OPENAI_REALTIME_MODEL=gpt-realtime
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
APP_PASSWORD=choose-a-long-private-password
SESSION_SECRET=replace-with-a-long-random-secret
SESSION_COOKIE_SECURE=false
```

Use `SESSION_COOKIE_SECURE=true` on an HTTPS deployment. Keep it `false` only for local HTTP testing. For safety, the server refuses to start with secure cookies enabled unless `APP_PASSWORD` is also set.

## Troubleshooting

**The call button says HTTPS is required**  
Open the public website through its `https://` address. Local testing should use `http://127.0.0.1:5000` or `http://localhost:5000`, not a plain-HTTP LAN address.

**The browser denied microphone access**  
Open the browser’s site permissions, allow the microphone, reload the page, and start the call again.

**The call button says an API key is missing**  
Add `OPENAI_API_KEY` to `.env` or to the hosting service’s secret environment variables, then restart the server.

**No sound is heard**  
Raise the device volume, make sure the in-call **Speaker** control is not muted, and check that the browser is allowed to play audio.

**The live captions are inaccurate**  
Choose the expected language in Settings, speak closer to the microphone, and reduce background noise.

**The conversation disappeared after a cloud restart**  
Attach persistent storage and point `DATABASE_PATH` to it. The included Render blueprint uses `/var/data/khotso.db`.

## Testing

```bash
python -m py_compile app.py companion_prompt.py
python -m unittest discover -s tests -v
node --check static/app.js
```

The automated tests mock the external AI response and Realtime handshake; an end-to-end spoken call still requires a valid API key, network access, microphone permission, and a supported browser. GitHub Actions runs the same checks on every proposed change.

## Important boundary

Khotso is a fictional AI companion, not a human, not conscious, and not legally or religiously married to the user. It is not a substitute for a real spouse or partner, family, friends, faith community, emergency services, medical care, mental-health care, legal advice, or financial advice.
