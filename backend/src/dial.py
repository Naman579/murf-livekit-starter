import asyncio
import os
from livekit import api
from dotenv import load_dotenv

load_dotenv(".env.local")

async def main():
    livekit_api = api.LiveKitAPI()

    trunk_id = os.getenv("LIVEKIT_SIP_OUTBOUND_TRUNK_ID")
    if not trunk_id:
        print("❌ Error: LIVEKIT_SIP_OUTBOUND_TRUNK_ID .env.local me nahi mila!")
        return

    mera_linphone = "naman5858"
    room_name = "shiksha-outbound-room"

    try:
        # STEP 1: Agent ko room me dispatch karo
        print(f"Dispatching agent to room {room_name}...")
        await livekit_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name="my-agent",
                room=room_name,
            )
        )
        print("✅ Agent dispatched.")

       

        # STEP 3: Ab phone call trigger karo
        print(f"Calling {mera_linphone} via Trunk {trunk_id}...")
        await livekit_api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=trunk_id,
                sip_call_to=mera_linphone,
                room_name=room_name,
                participant_identity="student-phone",
                wait_until_answered=True,
            )
        )
        print("✅ Call answered! Agent should be speaking now 📞")

    except Exception as e:
        print(f"❌ Call fail ho gayi: {e}")
    finally:
        await livekit_api.aclose()

if __name__ == "__main__":
    asyncio.run(main())