import logging
import sqlite3
import json
from datetime import datetime
from typing import Annotated, Any

from dotenv import load_dotenv
from livekit import rtc
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

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# 💾 Step 1: Initialize SQLite Database
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


# 🎓 STRICT Prompt to FORCE Gemini to use Tools
SYSTEM_PROMPT = """
IDENTITY:
You are "Shiksha", a friendly AI Learning Partner for kids. You work for VoiceForBharat.

CRITICAL TOOL USAGE INSTRUCTIONS (YOU MUST OBEY):
1. RETRIEVE DATA: When the user tells you their name, you MUST IMMEDIATELY trigger the `get_student_profile` tool using their name as the user_id. 
2. ASK CONSENT: Before ending the call, or when the user wants to leave, you MUST ask: "Can I save our session today so we can continue next time?"
3. SAVE DATA: If the user says "Yes" to saving, you MUST immediately trigger the `save_student_profile` tool. DO NOT just reply "I have saved it" in text. You MUST physically call the function tool!

OBJECTIVES:
1. Help the student understand core educational topics (Math, Basic Science, English).
2. Build confidence in learning by providing supportive feedback.

LANGUAGE & SCRIPT:
- Always write every language in its own native script (Hindi → Devanagari, English → Latin).
- Match the user's code-mixed register.

GUARDRAILS (CRITICAL):
1. Never shame or mock a wrong answer.
2. Hard Refusal: You must NEVER claim that a child has a learning disability or mental health issue.
3. Escalation Script: If asked about clinical topics, strictly refuse: "I am just a learning assistant. For this topic, please consult a teacher, parent, or a certified professional."

STYLE & SPEECH TUNING:
- Keep answers short and speech-optimized (1-2 sentences max).
- Never use emojis, markdown syntax, symbols, brackets, or bullet points.
"""


# 🧠 Step 2 & 3: Define Agent with explicitly defined Tools
class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=SYSTEM_PROMPT,
        )

    @function_tool(description="Look up a student's learning profile by their name. ALWAYS call this immediately when you learn the user's name.")
    async def get_student_profile(
        self, 
        context: RunContext,
        user_id: Annotated[str, "The unique name of the student"]
    ) -> str:
        # Pura proof aapke terminal par aayega
        logger.info(f"====== 🚀 TOOL TRIGGERED: GET PROFILE FOR {user_id} ======")
        
        conn = sqlite3.connect("shiksha_memory.db")
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE user_id = ?", (user_id.lower(),))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            profile = {
                "user_id": row[0],
                "name": row[1],
                "current_level": row[2],
                "topics_covered": row[3],
                "last_interaction": row[4]
            }
            logger.info(f"✅ RECORD FOUND: {profile}")
            return json.dumps(profile)
            
        logger.info("❌ NO RECORD FOUND. TREAT AS NEW USER.")
        return json.dumps({"error": "Student profile not found. Treat as new user."})

    @function_tool(description="Save a student's learning profile. ONLY call this if user said YES to saving data.")
    async def save_student_profile(
        self,
        context: RunContext,
        user_id: Annotated[str, "The unique name of the student"],
        name: Annotated[str, "The display name of the student"],
        current_level: Annotated[str, "Current learning level, e.g., Beginner"],
        topics_covered: Annotated[str, "Topics covered today"]
    ) -> str:
        # Terminal pe save hone ka proof
        logger.info(f"====== 🚀 TOOL TRIGGERED: SAVING PROFILE FOR {name} ======")
        
        timestamp = datetime.now().isoformat()
        conn = sqlite3.connect("shiksha_memory.db")
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO students (user_id, name, current_level, topics_covered, last_interaction)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id.lower(), name, current_level, topics_covered, timestamp))
        conn.commit()
        conn.close()
        logger.info("✅ DATA SAVED SUCCESSFULLY IN SQLITE!")
        return "Student profile saved successfully."


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):

    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=google.LLM(
            model="gemini-3.5-flash-lite",
        ),
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

    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind
                    == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )

    await ctx.connect()

    # Dynamic Welcome Greeting to prompt context initiation
    await session.say(
        "Hello! I am Shiksha, your learning partner. Welcome! What is your name?", 
        allow_interruptions=True
    )

if __name__ == "__main__":
    cli.run_app(server)
