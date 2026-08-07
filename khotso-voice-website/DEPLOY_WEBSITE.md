# Deploy Khotso as an HTTPS Website

This package is ready for a Python/Docker hosting service. In the GitHub profile repository, the repository-root `render.yaml` is configured for Render-style blueprint deployment and points to the `khotso-voice-website/` source directory. The exact buttons and prices on a hosting service can change, so review the host’s current dashboard before completing deployment.

## 1. Prepare a private repository

1. Create a **private** Git repository.
2. Add all files from this folder.
3. Do not add `.env`; it is excluded by `.gitignore`.
4. Push the repository to your source-code host.

## 2. Create the web service

Use the repository-root `render.yaml` as a blueprint. For a manually created service, set the service root directory to `khotso-voice-website` and use:

- Build command: `python -m py_compile app.py companion_prompt.py`
- Start command: `python app.py`
- Health check: `/health`
- Port: supplied automatically by the host through `PORT`

## 3. Set private environment variables

Set these in the hosting dashboard—never in browser code:

```text
OPENAI_API_KEY=<your real API key>
OPENAI_MODEL=gpt-5
OPENAI_REALTIME_MODEL=gpt-realtime
OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe
APP_PASSWORD=<a long private password>
SESSION_SECRET=<a long random secret>
SESSION_COOKIE_SECURE=true
DATABASE_PATH=/var/data/khotso.db
```

Generate `SESSION_SECRET` as a long random string. Keep `APP_PASSWORD` different from other passwords you use.

## 4. Attach persistent storage

Mount a persistent disk at `/var/data`. Without persistent storage, messages and settings may disappear when the host rebuilds or restarts the service.

## 5. Test the website

1. Open the host’s HTTPS URL.
2. Sign in.
3. Open Settings and confirm the live voice.
4. Tap **Call Khotso**.
5. Allow microphone access.
6. Speak a sentence and confirm that you hear a spoken reply and see both transcripts.
7. End the call and verify that the transcript appears in the message history.

## 6. Add it to a phone home screen

On Android Chrome, open the browser menu and choose **Add to Home screen** or **Install app**. On iPhone Safari, use **Share → Add to Home Screen**.

## Security checklist

- Keep the repository private.
- Never commit `.env` or an API key.
- Keep `APP_PASSWORD` enabled.
- Use only HTTPS online.
- Keep the persistent disk private.
- Export and store conversation files carefully.
- Rotate the API key and password immediately if either is exposed.
