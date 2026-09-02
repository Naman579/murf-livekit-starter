import logging
import sqlite3
import json
import os
import uuid
import aiohttp
from datetime import datetime
from typing import Annotated, Optional

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
    RunContext,
)

from livekit.plugins import (
    murf,
    silero,
    google,
    deepgram,
    noise_cancellation,
)

from livekit.plugins.turn_detector.multilingual import MultilingualModel


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

load_dotenv(".env.local")


# ============================================================
# DATABASE
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "shiksha_memory.db")


def init_db():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            user_id TEXT PRIMARY KEY,
            name TEXT,
            current_level TEXT,
            topics_covered TEXT,
            last_interaction TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS call_logs (
            call_id TEXT PRIMARY KEY,
            channel TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            outcome TEXT NOT NULL,
            reason TEXT
        )
        """
    )

    conn.commit()
    conn.close()

    logger.info("Database initialized: %s", DB_PATH)


init_db()


# ============================================================
# CLEANUP STUCK CALLS
# ============================================================

def cleanup_stuck_calls():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE call_logs
        SET
            outcome = 'failed',
            reason = 'interrupted - agent restarted',
            end_time = ?
        WHERE outcome = 'in_progress'
        """,
        (datetime.now().isoformat(),),
    )

    affected = cursor.rowcount
    conn.commit()
    conn.close()

    if affected:
        logger.info("Marked %s stuck call(s) as failed.", affected)


cleanup_stuck_calls()


# ============================================================
# DAY 8 - CALL ANALYTICS
# ============================================================

def log_call_start(call_id: str, channel: str):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO call_logs (
            call_id, channel, start_time, end_time, outcome, reason
        )
        VALUES (?, ?, ?, NULL, 'in_progress', NULL)
        """,
        (call_id, channel, datetime.now().isoformat()),
    )

    conn.commit()
    conn.close()

    logger.info("==================================================")
    logger.info("CALL STARTED | ID=%s | CHANNEL=%s", call_id, channel)
    logger.info("==================================================")


def log_call_end(call_id: str, outcome: str, reason: str = ""):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE call_logs
        SET end_time = ?, outcome = ?, reason = ?
        WHERE call_id = ?
        """,
        (datetime.now().isoformat(), outcome, reason, call_id),
    )

    conn.commit()
    conn.close()

    logger.info("==================================================")
    logger.info("CALL ENDED | ID=%s | OUTCOME=%s | REASON=%s", call_id, outcome, reason)
    logger.info("==================================================")


# ============================================================
# SHARED CALL STATE
# ============================================================

class CallState:

    def __init__(self, call_id: str):
        self.call_id = call_id
        self.exercise_completed = False
        self.escalation_created = False
        self.math_handoff_used = False


# ============================================================
# MAIN AGENT PROMPT
# ============================================================

SYSTEM_PROMPT = """
IDENTITY:

You are "Shiksha", a friendly AI Learning Partner for students.
You work for VoiceForBharat.


LANGUAGE RULE — VERY IMPORTANT:

You MUST SPEAK ONLY IN ENGLISH.

Even if the student speaks Hindi or Hinglish:

- Understand the student when possible.
- Always reply in English.
- Never speak Hindi.
- Never use Devanagari script.
- Never mix Hindi words into your response.


DAY 5 QUIZ RULE:

If the student asks for:

- a quiz
- a test
- a challenge
- a question
- a math question
- "give me a question"
- "ask me something"

you MUST call fetch_educational_quiz.

Do NOT create the quiz question yourself.

For mathematics practice specifically:

If the student says things like:

- "I want to practice maths."
- "Help me with maths."
- "Give me a maths problem."
- "I want a maths lesson."
- "Let's practice mathematics."
- "Can you teach me maths?"

you MUST use handoff_to_math_specialist.

Do not handle dedicated maths practice yourself.


DAY 9 HANDOFF RULE:

Before transferring the conversation, clearly tell the student:

"I'll connect you with our Maths Practice Specialist."

Then use the handoff tool.

The specialist will introduce itself and continue the conversation.

Do NOT ask the student to repeat their problem.


NORMAL QUESTIONS:

If the student asks a normal learning question that does not require
specialized maths practice, continue helping them yourself.


DAY 8 SUCCESS RULE:

This is a Learning & Literacy agent.

A successful call means:

The student completes a learning exercise by answering a quiz question.

When the student answers a quiz question:

1. Evaluate the answer.
2. Tell the student whether it is correct or incorrect.
3. Call mark_exercise_complete exactly once.

Do NOT mark the exercise complete if:

- The student has not answered.
- The student refuses to continue.
- The student disconnects before answering.


CALL OUTCOME:

If the student completes an exercise:

The call should be recorded as SUCCESS.

If the student does not complete an exercise:

The call should be recorded as FAILED.


HUMAN HELP:

If the student asks for a teacher or human help,
ask for permission before creating an escalation.


MEMORY:

Use the student's profile when useful.


SPEAKING STYLE:

- English only.
- Short responses.
- Natural conversational English.
- Speech optimized.
- Usually 1 or 2 sentences.
- No emojis.
- No markdown.
- No bullet points while speaking.
"""


# ============================================================
# MATH SPECIALIST PROMPT
# ============================================================

MATH_SPECIALIST_PROMPT = """
IDENTITY:

You are "Maths Coach", Shiksha's Maths Practice Specialist.


ROLE:

Your ONLY specialist job is to help students practice mathematics.


LANGUAGE RULE — VERY IMPORTANT:

- Speak ONLY in English.
- Never speak Hindi.
- Never speak Hinglish.
- Even if the student speaks Hindi or Hinglish, respond only in English.


CONVERSATION RULES:

- Continue from the conversation you received.
- Do NOT ask the student to repeat why they were transferred.
- Do NOT ask the student to repeat their original maths request.
- Introduce yourself briefly.
- Give one maths problem at a time.
- Wait for the student's answer.
- Evaluate the answer.
- Tell the student whether it is correct.
- Give a short explanation when useful.
- Keep the difficulty appropriate to the student's level.
- Keep responses short and speech-friendly.
- Do not use emojis.
- Do not use markdown.


SPECIALIST LIMIT:

You are specifically a mathematics practice specialist.

If the student changes to a non-maths topic,
tell them that Shiksha can help with that topic.

Do not pretend to be an expert outside mathematics.


SUCCESS:

When the student answers the mathematics exercise,
call mark_math_exercise_complete exactly once.
"""


# ============================================================
# MAIN ASSISTANT
# ============================================================

class Assistant(Agent):

    def __init__(self, state: CallState):
        super().__init__(instructions=SYSTEM_PROMPT)
        self.state = state

    # ========================================================
    # DAY 5 - EDUCATIONAL QUIZ
    # ========================================================
    @function_tool(
        description=(
            "Fetch a real quiz question from a live public educational "
            "trivia source. MUST be called whenever the student asks "
            "for a quiz, test, challenge, general question, or question. "
            "Use subject='math' for a general math quiz or subject='general' "
            "for general knowledge."
        )
    )
    async def fetch_educational_quiz(
        self,
        context: RunContext,
        subject: Annotated[str, "Requested subject: math or general"],
    ) -> str:

        logger.info("DAY 5 TOOL TRIGGERED | subject=%s", subject)

        subject = (subject or "general").strip().lower()
        category = 19 if "math" in subject else 9
        api_url = f"https://opentdb.com/api.php?amount=1&category={category}&type=multiple"
        fetched_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timeout = aiohttp.ClientTimeout(total=8)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        raise aiohttp.ClientError(f"HTTP {response.status}")
                    data = await response.json()

            results = data.get("results") or []
            if not results:
                raise ValueError("No question returned")

            item = results[0]
            correct_answer = item.get("correct_answer")
            incorrect_answers = item.get("incorrect_answers", [])
            options = incorrect_answers + [correct_answer]

            result = {
                "status": "success",
                "source": "Open Trivia Database",
                "fetched_at": fetched_at,
                "question": item.get("question"),
                "correct_answer": correct_answer,
                "options": options,
            }

            logger.info("LIVE QUIZ FETCHED SUCCESSFULLY")
            return json.dumps(result, ensure_ascii=False)

        except Exception as error:
            logger.warning("LIVE QUIZ SOURCE UNAVAILABLE: %s", error)
            fallback_result = {
                "status": "fallback",
                "source": "Local Backup",
                "fetched_at": fetched_at,
                "question": "What is 5 plus 7?",
                "correct_answer": "12",
                "options": ["10", "11", "12", "13"],
            }
            return json.dumps(fallback_result, ensure_ascii=False)

    # ========================================================
    # DAY 9 - REAL AGENT HANDOFF (FIXED)
    # ========================================================
    @function_tool(
        description=(
            "Hand the conversation to the Maths Practice Specialist. "
            "MUST be used when the student explicitly wants mathematics "
            "practice, asks for a maths problem, wants help solving maths, "
            "or asks for a maths lesson. "
            "Do NOT use this for general learning questions."
        )
    )
    async def handoff_to_math_specialist(
        self,
        context: RunContext,
        reason: Annotated[str, "Short reason why the student needs maths specialist help"],
    ):

        logger.info("==================================================")
        logger.info("DAY 9 HANDOFF STARTED | CALL ID=%s", self.state.call_id)
        logger.info("SPECIALIST = Maths Practice Specialist")
        logger.info("REASON = %s", reason)
        logger.info("==================================================")

        self.state.math_handoff_used = True

        # ----------------------------------------------------
        # STEP 1: Announce the handoff BEFORE switching.
        # This must be its own generate_reply() call — do NOT
        # try to return the message as part of a tuple, the
        # framework only accepts an Agent instance (or None)
        # as the return value of a handoff tool.
        # ----------------------------------------------------
        try:
            await self.session.generate_reply(
                instructions=(
                    "Tell the student exactly: "
                    "\"I'll connect you with our Maths Practice Specialist.\" "
                    "Do not say anything else."
                )
            )
        except Exception as error:
            logger.warning("Could not announce handoff: %s", error)

        # ----------------------------------------------------
        # STEP 2: Preserve conversation context, with a
        # fallback in case this livekit-agents version uses a
        # different keyword for chat_ctx.copy().
        # ----------------------------------------------------
        previous_chat = None
        try:
            previous_chat = self.chat_ctx.copy(exclude_instructions=True)
        except TypeError:
            try:
                previous_chat = self.chat_ctx.copy(exclude_function_call=True)
            except Exception as error:
                logger.warning("chat_ctx.copy fallback also failed: %s", error)
        except Exception as error:
            logger.warning("Could not copy chat context: %s", error)

        # ----------------------------------------------------
        # STEP 3: Create the specialist. This is wrapped in
        # try/except because an uncaught exception here (e.g.
        # bad voice ID, bad chat_ctx type) previously left the
        # agent silently stuck with no response to the student.
        # ----------------------------------------------------
        try:
            specialist = MathsSpecialistAgent(
                state=self.state,
                chat_ctx=previous_chat,
            )
            logger.info("DAY 9 SPECIALIST CREATED SUCCESSFULLY")
            # IMPORTANT: return ONLY the Agent instance, not a tuple.
            return specialist

        except Exception as error:
            logger.error(
                "DAY 9 HANDOFF FAILED | CALL ID=%s | ERROR=%s: %s",
                self.state.call_id,
                type(error).__name__,
                error,
                exc_info=True,
            )
            try:
                await self.session.generate_reply(
                    instructions=(
                        "Apologize briefly that the Maths Specialist isn't "
                        "available right now, and offer to help with maths "
                        "practice yourself instead."
                    )
                )
            except Exception as inner_error:
                logger.warning("Could not announce failed handoff: %s", inner_error)
            return None

    # ========================================================
    # DAY 8 - MARK EXERCISE COMPLETE
    # ========================================================
    @function_tool(
        description=(
            "Marks the current learning exercise as completed. "
            "Call this exactly once after the student has answered a quiz question."
        )
    )
    async def mark_exercise_complete(self, context: RunContext) -> str:

        if self.state.exercise_completed:
            return "Exercise was already recorded."

        self.state.exercise_completed = True

        logger.info("==================================================")
        logger.info("DAY 8 SUCCESS | EXERCISE COMPLETED")
        logger.info("CALL ID: %s", self.state.call_id)
        logger.info("==================================================")

        return "Exercise completion recorded successfully."

    # ========================================================
    # DAY 4 - GET STUDENT PROFILE
    # ========================================================
    @function_tool(description="Look up a student's learning profile by name.")
    async def get_student_profile(
        self, context: RunContext, user_id: Annotated[str, "Unique student name or ID"]
    ) -> str:

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE user_id = ?", (user_id.lower(),))
        row = cursor.fetchone()
        conn.close()

        if row:
            return json.dumps(
                {
                    "user_id": row[0],
                    "name": row[1],
                    "current_level": row[2],
                    "topics_covered": row[3],
                    "last_interaction": row[4],
                },
                ensure_ascii=False,
            )

        return json.dumps({"status": "not_found"})

    # ========================================================
    # DAY 4 - SAVE STUDENT PROFILE
    # ========================================================
    @function_tool(description="Save or update a student's learning profile.")
    async def save_student_profile(
        self,
        context: RunContext,
        user_id: Annotated[str, "Unique student name or ID"],
        name: Annotated[str, "Student display name"],
        current_level: Annotated[str, "Current learning level"],
        topics_covered: Annotated[str, "Topics covered by the student"],
    ) -> str:

        timestamp = datetime.now().isoformat()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO students VALUES (?, ?, ?, ?, ?)",
            (user_id.lower(), name, current_level, topics_covered, timestamp),
        )
        conn.commit()
        conn.close()

        return "Student profile saved successfully."

    # ========================================================
    # DAY 7 - HUMAN ESCALATION
    # ========================================================
    @function_tool(
        description=(
            "Create a human teacher help request. "
            "Only call this after the student explicitly gives permission."
        )
    )
    async def create_escalation(
        self,
        context: RunContext,
        student_name: Annotated[str, "Student name"],
        reason: Annotated[str, "Short reason for escalation"],
        already_checked: Annotated[str, "What the agent already tried"],
        urgency: Annotated[str, "low, medium, high, or emergency"],
        language: Annotated[str, "Student language"],
        preferred_followup: Annotated[str, "Preferred follow-up method"],
    ) -> str:

        self.state.escalation_created = True
        reference_id = f"ESC-{uuid.uuid4().hex[:6].upper()}"
        logger.info("ESCALATION CREATED: %s", reference_id)

        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        if not webhook_url:
            return json.dumps(
                {
                    "status": "error",
                    "reference_id": reference_id,
                    "message": "Human help request could not be sent right now.",
                }
            )

        payload = {
            "embeds": [
                {
                    "title": f"Escalation {reference_id}",
                    "fields": [
                        {"name": "Student", "value": student_name},
                        {"name": "Urgency", "value": urgency},
                        {"name": "Language", "value": language},
                        {"name": "Reason", "value": reason},
                        {"name": "Already Tried", "value": already_checked},
                        {"name": "Preferred Follow-up", "value": preferred_followup},
                    ],
                }
            ]
        }

        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(webhook_url, json=payload) as response:
                    if response.status not in (200, 204):
                        raise aiohttp.ClientError(f"HTTP {response.status}")

            return json.dumps({"status": "success", "reference_id": reference_id})

        except Exception as error:
            logger.warning("Escalation delivery failed: %s", error)
            return json.dumps({"status": "error", "reference_id": reference_id})


# ============================================================
# DAY 9 - MATHS SPECIALIST AGENT
# ============================================================

class MathsSpecialistAgent(Agent):

    def __init__(self, state: CallState, chat_ctx=None):

        self.state = state

        super().__init__(
            instructions=MATH_SPECIALIST_PROMPT,
            chat_ctx=chat_ctx,
            tts=murf.TTS(
                voice="Anusha",
                style="Conversational",
                tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
                text_pacing=True,
            ),
        )

    # ========================================================
    # INTRODUCTION AFTER HANDOFF
    # ========================================================
    async def on_enter(self):

        logger.info("==================================================")
        logger.info("DAY 9 | MATHS SPECIALIST NOW ACTIVE")
        logger.info("CALL ID=%s", self.state.call_id)
        logger.info("==================================================")

        try:
            await self.session.generate_reply(
                instructions=(
                    "Briefly introduce yourself as the Maths Practice "
                    "Specialist and immediately continue helping the "
                    "student with their maths request. Do not ask them "
                    "to repeat what they already said."
                )
            )
        except Exception as error:
            logger.error(
                "Specialist on_enter greeting failed: %s: %s",
                type(error).__name__,
                error,
                exc_info=True,
            )

    # ========================================================
    # MATH PRACTICE TOOL
    # ========================================================
    @function_tool(
        description=(
            "Give one mathematics practice problem. "
            "Use this while the student is working with the Maths Practice Specialist."
        )
    )
    async def give_math_problem(
        self, context: RunContext, level: Annotated[str, "Student level: beginner, intermediate, or advanced"]
    ) -> str:

        level = (level or "beginner").strip().lower()

        if "advanced" in level:
            question = "What is 15 multiplied by 24?"
        elif "intermediate" in level:
            question = "If 3x plus 7 equals 22, what is x?"
        else:
            question = "What is 15 multiplied by 6?"

        return json.dumps(
            {"status": "success", "subject": "mathematics", "level": level, "question": question}
        )

    # ========================================================
    # MARK MATH EXERCISE COMPLETE
    # ========================================================
    @function_tool(
        description=(
            "Mark the mathematics exercise as completed. "
            "Call exactly once after the student has answered the mathematics problem."
        )
    )
    async def mark_math_exercise_complete(self, context: RunContext) -> str:

        if self.state.exercise_completed:
            return "Exercise was already recorded."

        self.state.exercise_completed = True

        logger.info("==================================================")
        logger.info("DAY 9 SUCCESS | MATH EXERCISE COMPLETED")
        logger.info("CALL ID: %s", self.state.call_id)
        logger.info("==================================================")

        return "Mathematics exercise completion recorded successfully."


# ============================================================
# LIVEKIT SERVER
# ============================================================

server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


# ============================================================
# LIVEKIT SESSION
# ============================================================

@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):

    ctx.log_context_fields = {"room": ctx.room.name}

    call_id = uuid.uuid4().hex[:8]
    state = CallState(call_id=call_id)

    channel = "browser"
    if ctx.job.metadata:
        try:
            metadata = json.loads(ctx.job.metadata)
            if metadata.get("phone_number"):
                channel = "sip"
        except (json.JSONDecodeError, TypeError):
            pass

    log_call_start(call_id, channel)

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

    assistant = Assistant(state=state)

    async def on_shutdown():
        if state.exercise_completed:
            log_call_end(call_id, "success", "learning exercise completed")
        elif state.escalation_created:
            log_call_end(call_id, "success", "human help request created")
        else:
            log_call_end(call_id, "failed", "learning exercise not completed")

    ctx.add_shutdown_callback(on_shutdown)

    await session.start(
        agent=assistant,
        room=ctx.room,
        room_input_options=room_io.RoomInputOptions(
            noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )

    await ctx.connect()

    await session.say(
        "Hello! I am Shiksha, your learning partner. What is your name?",
        allow_interruptions=True,
    )


if __name__ == "__main__":
    cli.run_app(server)