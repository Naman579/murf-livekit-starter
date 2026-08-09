# Day 5 – The Tools 🎓
**Project:** Shiksha – AI Learning Partner (Learning & Literacy track)
**Challenge:** 10 Days of Voice Agents — #VoiceForBharat
**Voice:** Murf Falcon TTS (`murf.TTS`, voice: Anisha)

## What I built
A function-call tool, `fetch_educational_quiz`, that fetches a real quiz/trivia
question for the student instead of the model making one up from memory.

## Is the data live or local?
**Live, with a local fallback.**
- Primary source: [numbersapi.com](http://numbersapi.com) — a free public API.
- `subject="math"` → hits `numbersapi.com/random/math`
- `subject="general"` → hits `numbersapi.com/random/trivia`
- If the request fails or times out (6s), the agent falls back to a **hand-built
  local backup question** ("What is 5 plus 7?"). This is stated explicitly so
  it's never confused with live data.

## How the tool is triggered
The model calls `fetch_educational_quiz` on its own whenever the student asks
for a quiz/question/challenge (e.g. "sawal do", "quiz khilao", "ask me
something"). It is **not** triggered manually — the tool description alone
tells the model when to call it. The model is instructed to never invent a
question itself; it must go through the tool.

## Freshness / timestamp
Every tool response (success or fallback) includes a `fetched_at` field with
the current date/time. The agent is instructed to mention this naturally
instead of assuming the data is fresh — so the student knows if it's a live
pull or a fallback.

## Failure handling
- Wrapped in `try/except` around the `aiohttp` call.
- On any failure (timeout, bad status, network error), the agent switches to
  the local backup question and tells the student — in natural conversational
  language, no technical words like "error" or "API" — that the live source
  wasn't reachable right now.
- No silent failures. No hallucinated questions.

## Memory chaining (Day 4 → Day 5)
If the student's name/profile is already known (`get_student_profile`), the
agent uses their `current_level` to personalize how it introduces the quiz
question (e.g. "since you're at Level 2, try this one") — without asking the
student to repeat information they already gave.

## Tech stack
- LiveKit Agents framework
- STT: Deepgram (`nova-3`, multilingual)
- LLM: Google Gemini (`gemini-3.5-flash-lite`)
- TTS: **Murf Falcon** (fastest TTS API), voice "Anisha"
- Storage: SQLite (`shiksha_memory.db`) for student profiles
- Tool data source: numbersapi.com (public, no auth)

## How to run
```bash
pip install -r requirements.txt   # livekit-agents, aiohttp, python-dotenv, etc.
python agent_day5_fixed.py
```
Requires a `.env.local` file with your LiveKit, Deepgram, Google, and Murf
API keys.

## Demo checklist
- ✅ Agent calls the tool automatically when asked for a quiz — no manual trigger
- ✅ Response is spoken naturally, not read out as JSON
- ✅ Killing the network / API produces a graceful spoken fallback, not silence
- ✅ Data source (live vs local) is stated clearly above
