# Privacy

Khotso stores settings, typed messages, and completed voice-call transcripts in the configured SQLite database. The application does not intentionally save raw microphone recordings.

Live audio, conversation context, profile text, and user-approved memory notes are sent to the configured OpenAI API so the companion can respond. Typed Responses API calls include `store=false`; OpenAI's applicable API data controls and abuse-monitoring policies still govern processing by the API provider.

Use the in-app export and clear controls carefully. Protect downloaded exports and database backups. Remove sensitive memory notes when they are no longer needed.
