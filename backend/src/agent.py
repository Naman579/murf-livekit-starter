import logging
import sqlite3
import json
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
    function_tool,
    RunContext
)
from livekit.plugins import murf, silero, google, deepgram
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

LANGUAGE & SCRIPT:
- Always write every language in its own native script (Hindi -> Devanagari, English -> Latin).

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
        # Real public API (Open Trivia DB) — HTTPS, no auth needed.
        # category 19 = Mathematics, category 9 = General Knowledge
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
            # Real failure path — honest, no invented answer, no silence.
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

    await session.start(agent=Assistant(), room=ctx.room)
    await ctx.connect()
    await session.say(
        "Hello! I am Shiksha, your learning partner. Welcome! What is your name?",
        allow_interruptions=True,
    )


if __name__ == "__main__":
    cli.run_app(server)
