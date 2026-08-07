# Khotso Voice Website Deployment Checklist

## Before uploading

- [ ] Keep the repository private.
- [ ] Confirm `.env` is not included.
- [ ] Confirm `data/khotso.db` is not included.
- [ ] Choose a long private `APP_PASSWORD`.
- [ ] Generate a long random `SESSION_SECRET`.
- [ ] Confirm the OpenAI API key has billing and model access.

## Hosting settings

- [ ] Set `OPENAI_API_KEY` as a secret.
- [ ] Set `APP_PASSWORD` as a secret.
- [ ] Set or generate `SESSION_SECRET`.
- [ ] Set `SESSION_COOKIE_SECURE=true` on HTTPS.
- [ ] Set `OPENAI_MODEL=gpt-5` or another compatible Responses API model available to the API project.
- [ ] Set `OPENAI_REALTIME_MODEL=gpt-realtime`.
- [ ] Set `OPENAI_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe`.
- [ ] Configure a persistent disk or volume for `DATABASE_PATH`.
- [ ] Ensure the health check uses `/health`.

## After deployment

- [ ] Open the HTTPS address.
- [ ] Confirm the password screen appears.
- [ ] Open Settings and confirm the names and profile.
- [ ] Tap **Call Khotso**.
- [ ] Grant microphone permission.
- [ ] Confirm the status changes to listening.
- [ ] Speak a test message and confirm an audible response.
- [ ] Confirm both voice transcripts appear in chat.
- [ ] Mute, unmute, interrupt, and end the call.
- [ ] Reload the page and confirm the transcript remains.
- [ ] Export a test conversation.
- [ ] Clear the test conversation.
- [ ] Add the site to the phone’s home screen.

## Security review

- [ ] Do not share the website password publicly.
- [ ] Do not put the API key into browser JavaScript.
- [ ] Review saved memory notes for sensitive information.
- [ ] Protect downloaded exports and database backups.
- [ ] Review hosting and API spending limits.
