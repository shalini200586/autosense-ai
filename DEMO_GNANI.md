# 45-second demo: Hindi / Hinglish voice with Gnani Prisma and Timbre

**Prerequisites (required for this demo):** a Gnani API key with Prisma STT and Timbre TTS enabled, set as `GNANI_API_KEY` in `.env` (then `docker compose up -d`). Open `http://localhost:8090/#/assistant` in Chrome or Edge on `localhost` and allow the microphone. The footer should read "Voice: Gnani Prisma … Timbre …" (not "Voice setup required"). Use a quiet room; speak for under ~25 s.

> Not yet verified with a live key at the time of writing. Run `GNANI_API_KEY=... pytest -k live_gnani` first; if your account lacks a language or voice, adjust `GNANI_STT_LANGUAGES` / `GNANI_TTS_VOICE_*` in `.env`.

| Time | Action | Say |
|---|---|---|
| 0:00–0:07 | Show the screen and the footer line naming Gnani Prisma and Timbre. | "This assistant uses Gnani Prisma for speech recognition and Timbre for speech synthesis, called from my server, so the key never reaches the browser." |
| 0:07–0:17 | Click the mic. **Speak:** "Mujhe barah lakh ke andar automatic SUV chahiye." Click the square to stop. Spinner: "Transcribing…". | (the spoken query) |
| 0:17–0:25 | The Prisma transcript appears as the user bubble (mic icon). The assistant replies with four verified cards. | "Prisma turned my Hinglish into text. The assistant searched live inventory and shows verified prices." |
| 0:25–0:35 | The reply is spoken automatically by Timbre (Hindi voice). Click **Listen** to replay. | "Timbre speaks the answer back. Voice is only the input and output layer; the answer is grounded in the database." |
| 0:35–0:45 | Optional: type or speak in Devanagari: "मुझे 10 लाख तक की ऑटोमैटिक SUV चाहिए". Show the Hindi reply. | "Same flow in Hindi. If speech fails, the app shows a clear error and chat keeps working." |

**If the key is missing:** the mic is disabled with "Voice setup required" and text chat is fully functional.
