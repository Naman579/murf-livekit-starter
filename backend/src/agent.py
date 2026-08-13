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
# DATABASE PATH
# ============================================================

# IMPORTANT:
# agent.py and dashboard.py must point to the SAME database.

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "shiksha_memory.db")


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_db():

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Day 4 - Student Memory
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

    # Day 8 - Call Analytics
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
        logger.info(
            "Marked %s stuck call(s) as failed.",
            affected,
        )


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
            call_id,
            channel,
            start_time,
            end_time,
            outcome,
            reason
        )
        VALUES (?, ?, ?, NULL, 'in_progress', NULL)
        """,
        (
            call_id,
            channel,
            datetime.now().isoformat(),
        ),
    )

    conn.commit()
    conn.close()

    logger.info(
        "=================================================="
    )
    logger.info(
        "CALL STARTED | ID=%s | CHANNEL=%s",
        call_id,
        channel,
    )
    logger.info(
        "=================================================="
    )


def log_call_end(
    call_id: str,
    outcome: str,
    reason: str = "",
):

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE call_logs
        SET
            end_time = ?,
            outcome = ?,
            reason = ?
        WHERE call_id = ?
        """,
        (
            datetime.now().isoformat(),
            outcome,
            reason,
            call_id,
        ),
    )

    conn.commit()
    conn.close()

    logger.info(
        "=================================================="
    )
    logger.info(
        "CALL ENDED | ID=%s | OUTCOME=%s | REASON=%s",
        call_id,
        outcome,
        reason,
    )
    logger.info(
        "=================================================="
    )


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
IDENTITY:
You are "Shiksha", a friendly AI Learning Partner for students.
You work for VoiceForBharat.

LANGUAGE RULE — VERY IMPORTANT:
You MUST speak ONLY in English.
Never speak Hindi.
Never use Devanagari script.
Even if the student speaks Hindi or Hinglish, respond only in English.

DAY 5 QUIZ RULE:
If the student asks for a quiz, challenge, test, math question,
or says "give me a question", "ask me something",
or "give me a quiz", you MUST call fetch_educational_quiz.

Do NOT create the quiz question yourself.

After receiving the tool result:
- Read the question naturally.
- Read the answer options naturally.
- Ask the student to answer.

If the live data source fails:
- Use the backup question from the tool.
- Tell the student naturally that you could not fetch a live question.
- Do NOT mention API, timeout, exception, server error, or technical details.

DAY 8 SUCCESS RULE:
This is a Learning & Literacy agent.

A successful call means:
The student completes a learning exercise by answering a quiz question.

When the student answers a quiz question:
1. Evaluate the answer.
2. Tell the student whether the answer is correct or incorrect.
3. Call mark_exercise_complete exactly once.

Do NOT mark the exercise complete if:
- The student has not answered.
- The student refuses to continue.
- The student disconnects before answering.

CALL OUTCOME:
If the student completes the exercise:
The call should be recorded as SUCCESS.

If the student does not complete the exercise:
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
- Do not use emojis.
- Do not use markdown.
- Do not use bullet points while speaking.
"""


# ============================================================
# ASSISTANT
# ============================================================

class Assistant(Agent):

    def __init__(self, call_id: str):

        super().__init__(
            instructions=SYSTEM_PROMPT
        )

        self.call_id = call_id

        # Day 8 analytics state
        self.exercise_completed = False
        self.escalation_created = False

    # ========================================================
    # DAY 5 - EDUCATIONAL QUIZ TOOL
    # ========================================================

    @function_tool(
        description=(
            "Fetch a real quiz question from a live public educational "
            "trivia source. MUST be called whenever the student asks "
            "for a quiz, test, challenge, math question, or question. "
            "Use subject='math' for math questions or subject='general' "
            "for general questions."
        )
    )
    async def fetch_educational_quiz(
        self,
        context: RunContext,
        subject: Annotated[
            str,
            "Requested subject: math or general",
        ],
    ) -> str:

        logger.info(
            "DAY 5 TOOL TRIGGERED | subject=%s",
            subject,
        )

        subject = (
            subject or "general"
        ).strip().lower()

        # Open Trivia Database categories
        # 19 = Mathematics
        # 9  = General Knowledge

        category = 19 if "math" in subject else 9

        api_url = (
            "https://opentdb.com/api.php"
            f"?amount=1&category={category}&type=multiple"
        )

        fetched_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        timeout = aiohttp.ClientTimeout(total=8)

        try:

            async with aiohttp.ClientSession(
                timeout=timeout
            ) as session:

                async with session.get(
                    api_url
                ) as response:

                    if response.status != 200:
                        raise aiohttp.ClientError(
                            f"HTTP {response.status}"
                        )

                    data = await response.json()

            results = data.get("results") or []

            if not results:
                raise ValueError(
                    "No question returned"
                )

            item = results[0]

            correct_answer = item.get(
                "correct_answer"
            )

            incorrect_answers = item.get(
                "incorrect_answers",
                [],
            )

            options = incorrect_answers + [
                correct_answer
            ]

            result = {
                "status": "success",
                "source": "Open Trivia Database",
                "fetched_at": fetched_at,
                "question": item.get("question"),
                "correct_answer": correct_answer,
                "options": options,
            }

            logger.info(
                "LIVE QUIZ FETCHED SUCCESSFULLY | source=Open Trivia Database"
            )

            return json.dumps(
                result,
                ensure_ascii=False,
            )

        except Exception as error:

            logger.warning(
                "LIVE QUIZ SOURCE UNAVAILABLE: %s",
                error,
            )

            fallback_result = {
                "status": "fallback",
                "source": "Local Backup",
                "fetched_at": fetched_at,
                "question": "What is 5 plus 7?",
                "correct_answer": "12",
                "options": [
                    "10",
                    "11",
                    "12",
                    "13",
                ],
            }

            return json.dumps(
                fallback_result,
                ensure_ascii=False,
            )

    # ========================================================
    # DAY 8 - MARK EXERCISE COMPLETE
    # ========================================================

    @function_tool(
        description=(
            "Marks the current learning exercise as completed. "
            "Call this exactly once after the student has answered "
            "a quiz question. Do not call it before the student answers."
        )
    )
    async def mark_exercise_complete(
        self,
        context: RunContext,
    ) -> str:

        # Prevent duplicate calls
        if self.exercise_completed:

            logger.info(
                "Exercise already marked complete."
            )

            return "Exercise was already recorded."

        self.exercise_completed = True

        logger.info(
            "=================================================="
        )
        logger.info(
            "DAY 8 SUCCESS | EXERCISE COMPLETED"
        )
        logger.info(
            "CALL ID: %s",
            self.call_id,
        )
        logger.info(
            "=================================================="
        )

        return (
            "Exercise completion recorded successfully."
        )

    # ========================================================
    # DAY 4 - GET STUDENT PROFILE
    # ========================================================

    @function_tool(
        description=(
            "Look up a student's learning profile by name."
        )
    )
    async def get_student_profile(
        self,
        context: RunContext,
        user_id: Annotated[
            str,
            "Unique student name or ID",
        ],
    ) -> str:

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT *
            FROM students
            WHERE user_id = ?
            """,
            (user_id.lower(),),
        )

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

        return json.dumps(
            {
                "status": "not_found"
            }
        )

    # ========================================================
    # DAY 4 - SAVE STUDENT PROFILE
    # ========================================================

    @function_tool(
        description=(
            "Save or update a student's learning profile."
        )
    )
    async def save_student_profile(
        self,
        context: RunContext,

        user_id: Annotated[
            str,
            "Unique student name or ID",
        ],

        name: Annotated[
            str,
            "Student display name",
        ],

        current_level: Annotated[
            str,
            "Current learning level",
        ],

        topics_covered: Annotated[
            str,
            "Topics covered by the student",
        ],
    ) -> str:

        timestamp = datetime.now().isoformat()

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO students
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id.lower(),
                name,
                current_level,
                topics_covered,
                timestamp,
            ),
        )

        conn.commit()
        conn.close()

        return "Student profile saved successfully."

    # ========================================================
    # DAY 7 - HUMAN ESCALATION
    # ========================================================

    @function_tool(
        description=(
            "Create a human teacher help request. Only call this "
            "after the student explicitly gives permission."
        )
    )
    async def create_escalation(
        self,
        context: RunContext,

        student_name: Annotated[
            str,
            "Student name",
        ],

        reason: Annotated[
            str,
            "Short reason for escalation",
        ],

        already_checked: Annotated[
            str,
            "What the agent already tried",
        ],

        urgency: Annotated[
            str,
            "low, medium, high, or emergency",
        ],

        language: Annotated[
            str,
            "Student language",
        ],

        preferred_followup: Annotated[
            str,
            "Preferred follow-up method",
        ],
    ) -> str:

        self.escalation_created = True

        reference_id = (
            f"ESC-{uuid.uuid4().hex[:6].upper()}"
        )

        logger.info(
            "ESCALATION CREATED: %s",
            reference_id,
        )

        webhook_url = os.getenv(
            "DISCORD_WEBHOOK_URL"
        )

        if not webhook_url:

            return json.dumps(
                {
                    "status": "error",
                    "reference_id": reference_id,
                    "message": (
                        "Human help request could not be sent right now."
                    ),
                }
            )

        payload = {
            "embeds": [
                {
                    "title": f"Escalation {reference_id}",
                    "fields": [
                        {
                            "name": "Student",
                            "value": student_name,
                        },
                        {
                            "name": "Urgency",
                            "value": urgency,
                        },
                        {
                            "name": "Language",
                            "value": language,
                        },
                        {
                            "name": "Reason",
                            "value": reason,
                        },
                        {
                            "name": "Already Tried",
                            "value": already_checked,
                        },
                        {
                            "name": "Preferred Follow-up",
                            "value": preferred_followup,
                        },
                    ],
                }
            ]
        }

        try:

            timeout = aiohttp.ClientTimeout(
                total=8
            )

            async with aiohttp.ClientSession(
                timeout=timeout
            ) as session:

                async with session.post(
                    webhook_url,
                    json=payload,
                ) as response:

                    if response.status not in (
                        200,
                        204,
                    ):
                        raise aiohttp.ClientError(
                            f"HTTP {response.status}"
                        )

            return json.dumps(
                {
                    "status": "success",
                    "reference_id": reference_id,
                }
            )

        except Exception as error:

            logger.warning(
                "Escalation delivery failed: %s",
                error,
            )

            return json.dumps(
                {
                    "status": "error",
                    "reference_id": reference_id,
                }
            )


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

@server.rtc_session(
    agent_name="my-agent"
)
async def my_agent(
    ctx: JobContext
):

    ctx.log_context_fields = {
        "room": ctx.room.name
    }

    # Unique call ID
    call_id = uuid.uuid4().hex[:8]

    # --------------------------------------------------------
    # Detect browser vs SIP
    # --------------------------------------------------------

    channel = "browser"

    if ctx.job.metadata:

        try:

            metadata = json.loads(
                ctx.job.metadata
            )

            if metadata.get("phone_number"):
                channel = "sip"

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            pass

    # --------------------------------------------------------
    # Record call start
    # --------------------------------------------------------

    log_call_start(
        call_id,
        channel,
    )

    # --------------------------------------------------------
    # Agent session
    # --------------------------------------------------------

    session = AgentSession(

        stt=deepgram.STT(
            model="nova-3",
            language="multi",
        ),

        llm=google.LLM(
            model="gemini-3.5-flash-lite",
        ),

        tts=murf.TTS(
            voice="Anisha",
            style="Conversation",

            tokenizer=tokenize.basic.SentenceTokenizer(
                min_sentence_len=2
            ),

            text_pacing=True,
        ),

        turn_detection=MultilingualModel(),

        vad=ctx.proc.userdata["vad"],

        preemptive_generation=True,
    )

    assistant = Assistant(
        call_id=call_id
    )

    # --------------------------------------------------------
    # CALL END HANDLER
    # --------------------------------------------------------

    async def on_shutdown():

        if assistant.exercise_completed:

            log_call_end(
                call_id,
                "success",
                "learning exercise completed",
            )

        elif assistant.escalation_created:

            log_call_end(
                call_id,
                "success",
                "human help request created",
            )

        else:

            log_call_end(
                call_id,
                "failed",
                "learning exercise not completed",
            )

    ctx.add_shutdown_callback(
        on_shutdown
    )

    # --------------------------------------------------------
    # Start session
    # --------------------------------------------------------

    await session.start(
        agent=assistant,
        room=ctx.room,

        room_input_options=room_io.RoomInputOptions(
            noise_cancellation=(
                noise_cancellation.BVCTelephony()
            ),
        ),
    )

    await ctx.connect()

    # --------------------------------------------------------
    # Greeting
    # --------------------------------------------------------

    await session.say(
        "Hello! I am Shiksha, your learning partner. "
        "What is your name?",
        allow_interruptions=True,
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    cli.run_app(server)