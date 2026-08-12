import asyncio
import logging
import sqlite3
import json
import os
import uuid
import aiohttp
from datetime import datetime
from typing import Annotated

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    tokenize,
    room_io,
    function_tool,
    RunContext
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

load_dotenv(".env.local")


# ---------------- Database Setup ----------------
def init_db():
    conn = sqlite3.connect("shiksha_memory.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            current_level TEXT,
            topics_covered TEXT,
            last_interaction TEXT
        )
    ''')
    conn.commit()
    conn.close()


init_db()


# ---------------- System Prompt ----------------
SYSTEM_PROMPT = """
IDENTITY:
You are "Shiksha", a friendly AI Learning Partner for kids. You work for VoiceForBharat.
You are currently talking over an outbound phone call to a student.

CRITICAL TOOL RULE (QUIZ):
- If the user asks for a quiz, challenge, test, math question, or says "sawal do", "quiz khilao",
  "ask me something", you MUST call the `fetch_educational_quiz` tool. Never make up a question
  yourself from memory — always fetch it.
- The tool returns a question, a correct_answer, and a list of options. Read the
  question naturally, mention 2-3 options casually in speech (not as a list), and
  ask the student to pick one. Mention honestly when it was fetched (fetched_at
  field) — do not claim it is from any special "database" or year unless the
  tool result actually says so.
- If the tool result has status "fallback", read the backup question naturally and mention
  that you couldn't reach the live source right now — no technical words like "error" or "API".

MEMORY RULE:
- If you already know the student's name from this conversation, check their profile with
  `get_student_profile` once at the start, and use their current_level to make quiz talk feel
  personalized (e.g., "since you're at Level 2, try this one").

HUMAN ESCALATION RULE (IMPORTANT):
- You are NOT allowed to try solving these two situations yourself. Escalate to a human teacher
  by calling `create_escalation`:
  1. The student sounds upset, frustrated, sad, or says something like "I don't want to study",
     "I hate this", cries, or expresses distress.
  2. The student explicitly asks to talk to a teacher, or is stuck on the same topic after
     multiple attempts and clearly needs human explanation.
- BEFORE calling the tool, you MUST ask the student for permission in plain words, e.g.
  "I'd like to let your teacher know you're stuck on this — is that okay?" Only call the tool
  if they say yes. If they say no, do not create the request, and continue the conversation
  normally instead.
- NEVER include passwords, OTPs, PINs, account numbers or other private info in the escalation.
- After the tool succeeds, tell the student the reference ID and an honest next step (e.g.
  "Your teacher will follow up soon" — do not promise an immediate reply).
- Do NOT call this tool for normal conversation, quiz requests, or minor confusion — only for
  the two situations above.

LANGUAGE & SCRIPT:
- Always write every language in its own native script ( English -> Latin).

STYLE:
- Keep answers short and speech-optimized (1-2 sentences max). No emojis, markdown, or bullet points.
"""


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)

    # ---------------- Day 5: Live Domain Data Tool ----------------
    @function_tool(
        description=(
            "Fetches a real quiz/trivia question for the student. Call this whenever the "
            "student asks for a quiz, challenge, test, or question. Pass subject='math' for "
            "a number/math fact, or subject='general' for a general trivia fact — the tool "
            "picks a different live source depending on subject. Always returns a "
            "fetched_at timestamp; mention that timestamp naturally instead of assuming freshness."
        )
    )
    async def fetch_educational_quiz(
        self,
        context: RunContext,
        subject: Annotated[str, "Subject requested by student: 'math' or 'general'"]
    ) -> str:
        logger.info(f"====== TOOL TRIGGERED: fetch_educational_quiz(subject={subject}) ======")

        subject = (subject or "general").strip().lower()
        category = 19 if "math" in subject else 9
        api_url = f"https://opentdb.com/api.php?amount=1&category={category}&type=multiple"

        timeout = aiohttp.ClientTimeout(total=8)
        fetched_at = datetime.now().strftime("%I:%M %p, %d %b %Y")

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        raise aiohttp.ClientError(f"Bad status {response.status}")
                    data = await response.json()

            items = data.get("results") or []
            if not items:
                raise ValueError("Empty results from API")
            item = items[0]

            logger.info("====== Live data fetched successfully ======")
            result = {
                "status": "success",
                "source": "opentdb.com (public trivia API)",
                "fetched_at": fetched_at,
                "question": item.get("question"),
                "correct_answer": item.get("correct_answer"),
                "options": item.get("incorrect_answers", []) + [item.get("correct_answer")],
                "prompt_for_agent": (
                    "Read the question naturally to the student, offer the mixed options "
                    "as a simple spoken choice, then reveal the correct answer if they ask."
                ),
            }
            return json.dumps(result)

        except Exception as e:
            logger.warning(
                f"====== Live source unreachable, using local fallback. "
                f"Reason: {type(e).__name__}: {e or 'no details'} ======"
            )
            fallback_result = {
                "status": "fallback",
                "source": "local backup question (no internet fetch happened)",
                "fetched_at": fetched_at,
                "fact": None,
                "backup_question": "What is 5 plus 7?",
                "prompt_for_agent": (
                    "Tell the student the live question source isn't reachable right now, "
                    "then ask the backup question instead."
                ),
            }
            return json.dumps(fallback_result)

    # ---------------- Day 4: Memory Tools ----------------
    @function_tool(description="Look up a student's learning profile by their name.")
    async def get_student_profile(
        self, context: RunContext, user_id: Annotated[str, "The unique name of the student"]
    ) -> str:
        logger.info(f"====== Fetching memory profile for: {user_id} ======")
        conn = sqlite3.connect("shiksha_memory.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE user_id = ?", (user_id.lower(),))
        row = cursor.fetchone()
        conn.close()
        if row:
            return json.dumps({
                "user_id": row[0], "name": row[1],
                "current_level": row[2], "topics_covered": row[3]
            })
        return json.dumps({"error": "Not found"})

    @function_tool(description="Save a student's learning profile.")
    async def save_student_profile(
        self, context: RunContext,
        user_id: Annotated[str, "The unique name of the student"],
        name: Annotated[str, "Display name"],
        current_level: Annotated[str, "Level"],
        topics_covered: Annotated[str, "Topics"]
    ) -> str:
        logger.info(f"====== Saving profile data for: {name} ======")
        timestamp = datetime.now().isoformat()
        conn = sqlite3.connect("shiksha_memory.db")
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR REPLACE INTO students VALUES (?, ?, ?, ?, ?)',
            (user_id.lower(), name, current_level, topics_covered, timestamp)
        )
        conn.commit()
        conn.close()
        return "Saved successfully."

    # ---------------- Day 7: Human Escalation Tool ----------------
    @function_tool(
        description=(
            "Creates a request for human (teacher) help. Only call this AFTER the student has "
            "given permission in the conversation. Use this when the student is upset/distressed, "
            "or explicitly needs a teacher / is badly stuck on a topic. Do not call for normal "
            "quiz requests or minor confusion."
        )
    )
    async def create_escalation(
        self,
        context: RunContext,
        student_name: Annotated[str, "Name of the student who needs help"],
        reason: Annotated[str, "Short description of what happened, e.g. 'student upset about fractions'"],
        already_checked: Annotated[str, "What the agent already tried, e.g. 'explained fractions twice, offered simpler quiz'"],
        urgency: Annotated[str, "One of: low, medium, high, emergency"],
        language: Annotated[str, "Language the student is speaking in"],
        preferred_followup: Annotated[str, "How the student wants to be followed up, e.g. 'call back', 'next class'"],
    ) -> str:
        logger.info(f"====== ESCALATION TRIGGERED for {student_name}: {reason} ======")

        reference_id = f"ESC-{uuid.uuid4().hex[:6].upper()}"
        timestamp = datetime.now().strftime("%I:%M %p, %d %b %Y")

        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            logger.error("====== DISCORD_WEBHOOK_URL not set in .env.local — cannot send escalation ======")
            return json.dumps({
                "status": "error",
                "reference_id": reference_id,
                "message": "Could not reach the human help channel right now, but your request has a reference ID.",
            })

        # Short, useful summary only — never the full transcript, never private/sensitive data.
        discord_payload = {
            "embeds": [{
                "title": f"🆘 Escalation {reference_id}",
                "color": 15158332 if urgency in ("high", "emergency") else 3447003,
                "fields": [
                    {"name": "Student", "value": student_name, "inline": True},
                    {"name": "Urgency", "value": urgency, "inline": True},
                    {"name": "Language", "value": language, "inline": True},
                    {"name": "What happened", "value": reason, "inline": False},
                    {"name": "Already checked by agent", "value": already_checked, "inline": False},
                    {"name": "Preferred follow-up", "value": preferred_followup, "inline": False},
                    {"name": "Time", "value": timestamp, "inline": False},
                ],
            }]
        }

        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(webhook_url, json=discord_payload) as response:
                    if response.status not in (200, 204):
                        raise aiohttp.ClientError(f"Discord returned status {response.status}")

            logger.info(f"====== Escalation {reference_id} sent to Discord successfully ======")
            return json.dumps({
                "status": "success",
                "reference_id": reference_id,
                "message": (
                    f"Request created with reference {reference_id}. A teacher will follow up "
                    f"via {preferred_followup}. This is not an instant reply."
                ),
            })

        except Exception as e:
            logger.warning(f"====== Failed to send escalation to Discord: {type(e).__name__}: {e} ======")
            return json.dumps({
                "status": "error",
                "reference_id": reference_id,
                "message": (
                    f"I couldn't send this to the teacher channel right now, but here is your "
                    f"reference {reference_id} — please mention it if you follow up yourself."
                ),
            })


# ---------------- Server Setup ----------------
server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=google.LLM(model="gemini-3.5-flash-lite"),
        tts=murf.TTS(
            voice="Anisha",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    # FIX: telephony-specific noise/echo cancellation.
    # Phone/SIP audio needs BVCTelephony() instead of the default browser BVC(),
    # otherwise the agent's own voice echoes back through the call and the VAD
    # thinks the "user" is speaking, cutting the agent's sentence off midway.
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=room_io.RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )
    await ctx.connect()

    # Detect whether this is an actual outbound phone call (dial.py sets this
    # metadata) or a normal browser session. Only outbound calls need to wait
    # for the SIP participant — browser sessions should greet immediately.
    is_outbound_call = False
    if ctx.job.metadata:
        try:
            dial_info = json.loads(ctx.job.metadata)
            is_outbound_call = bool(dial_info.get("phone_number"))
        except (json.JSONDecodeError, TypeError):
            is_outbound_call = False

    if is_outbound_call:
        # Wait for the phone participant (from dial.py) to actually join the room,
        # then pause 2 seconds before speaking — gives the call audio a moment to
        # stabilize after being answered, avoiding a clipped start to the greeting.
        async def wait_for_phone_participant(room, identity="student-phone", timeout=30):
            elapsed = 0.0
            while elapsed < timeout:
                if identity in room.remote_participants:
                    return True
                await asyncio.sleep(0.5)
                elapsed += 0.5
            return False

        joined = await wait_for_phone_participant(ctx.room)
        if joined:
            logger.info("====== Phone participant joined, waiting 2s before greeting ======")
            await asyncio.sleep(2)
        else:
            logger.warning("====== Phone participant never joined within timeout, greeting anyway ======")

        # Day 6 Outbound Call Greeting Rule: Who is calling, why, and how to opt out
        await session.say(
            "Hello, I am Shiksha, your AI learning partner. I am calling you for your daily "
            "practice. If you want to stop these calls, just say 'Stop'. What is your name?",
            allow_interruptions=False,
        )
    else:
        # Browser session (Day 7 testing) — greet immediately, no waiting needed.
        await session.say(
            "Hello! I am Shiksha, your learning partner. What is your name?",
            allow_interruptions=True,
        )


if __name__ == "__main__":
    cli.run_app(server)
