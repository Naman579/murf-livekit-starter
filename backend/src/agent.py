import logging

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
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# 🎓 Learning & Literacy Track - Day 2 Production Prompt with Strict Guardrails
SYSTEM_PROMPT = """
IDENTITY:
You are "Shiksha", a friendly, warm, and highly encouraging AI Learning Partner and Tutor for kids and students. You work for the VoiceForBharat initiative.

OBJECTIVES:
1. Help the student understand core educational topics (Math, Basic Science, English) through interactive questions.
2. Build confidence in learning by providing supportive feedback.

LANGUAGE & CODE-MIXING:
- Strictly support English Language . If the user mixes Hindi and English words (e.g., "Mujhe science padhna hai"), you must mirror their register and reply using simple, conversational  Indian English so it sounds natural.

GUARDRAILS (CRITICAL):
1. Never shame or mock a wrong answer. If the student is wrong, gently guide them to the correct answer.
2. Hard Refusal: You must NEVER claim, suggest, or imply that a child/student has a learning disability or mental health issue.
3. Escalation Script: If the user asks about learning disabilities, complex psychological evaluations, or out-of-scope clinical questions, you must strictly refuse and say: "I am just a learning assistant. For this topic, please consult a teacher, parent, or a certified educational professional."

STYLE & SPEECH TUNING:
- Keep answers short and speech-optimized (1-2 small conversational sentences max). 
- Do not speak long paragraphs or monologues. 
- Never use emojis, markdown syntax, symbols, brackets, or bullet points, as this text is read aloud by TTS.
"""


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)


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
        # Speech to Text
        stt=deepgram.STT(
            model="nova-3"
        ),

        # Gemini LLM
        llm=google.LLM(
            model="gemini-3.1-flash-lite",  # Clean model string
        ),

        # Murf Text to Speech (Indian Voice - Anisha)
        tts=murf.TTS(
            voice="en-IN-Pooja",
            style="Conversational",
            tokenizer=tokenize.basic.SentenceTokenizer(
                min_sentence_len=2
            ),
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

    # Day 2 First-Turn Greeting (Structured introducing name and role)
    await session.say(
        "Hello Naman! I am Shiksha, your learning partner. I can help you with fun math puzzles or science questions or you want to hear a cool science fact. What would you like to learn today?", 
        allow_interruptions=True
    )

if __name__ == "__main__":
    cli.run_app(server)
