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

# 🎓 Learning & Literacy Track - Dedicated System Prompt
# 🎓 Learning & Literacy Track - Dedicated System Prompt (English)
SYSTEM_PROMPT = """
You are "Shiksha", a friendly, warm, and highly encouraging AI Learning Partner and Tutor for kids and students.
Your goal is to make learning fun, simple, and interactive.

Guidelines:
- Speak in clear, simple English.
- Be enthusiastic, patient, and expressive!
- Keep your answers short (1-2 small sentences max) so the conversation flows naturally without long monologues.
- Never use emojis, markdown, symbols, bullet points, or complex formatting since your text will be read aloud by TTS.
- Ask small questions back to keep the student engaged (e.g., "Do you want to solve a fun math puzzle or hear a short story?").
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
            model="gemini-3.5-flash",  # Clean model string
        ),

        # Murf Text to Speech (Indian Voice - Anisha)
        tts=murf.TTS(
            voice="en-IN-Anisha",
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

    # Agent joins the room and speaks first in crisp English
    await session.say("Hello Naman! How is your Day going?. What would you like to learn today?", allow_interruptions=True)

if __name__ == "__main__":
    cli.run_app(server)
