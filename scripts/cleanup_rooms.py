#!/usr/bin/env python3
"""
Cleanup all active LiveKit rooms.

Usage:
    python scripts/cleanup_rooms.py          # Interactive (asks confirmation)
    python scripts/cleanup_rooms.py --force  # Delete all without asking
    python scripts/cleanup_rooms.py --list   # Only list, don't delete
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from livekit.api import LiveKitAPI, ListRoomsRequest, DeleteRoomRequest

load_dotenv()


async def main():
    url = os.getenv("LIVEKIT_URL")
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not all([url, api_key, api_secret]):
        print("Error: LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET must be set in .env")
        sys.exit(1)

    lk = LiveKitAPI(url, api_key, api_secret)
    rooms = await lk.room.list_rooms(ListRoomsRequest())

    if not rooms.rooms:
        print("No active rooms.")
        await lk.aclose()
        return

    print(f"\nActive rooms: {len(rooms.rooms)}\n")
    for r in rooms.rooms:
        print(f"  {r.name}  |  participants: {r.num_participants}  |  sid: {r.sid}")

    if "--list" in sys.argv:
        await lk.aclose()
        return

    if "--force" not in sys.argv:
        answer = input(f"\nDelete all {len(rooms.rooms)} room(s)? [y/N]: ")
        if answer.lower() != "y":
            print("Cancelled.")
            await lk.aclose()
            return

    print()
    for r in rooms.rooms:
        try:
            await lk.room.delete_room(DeleteRoomRequest(room=r.name))
            print(f"  Deleted: {r.name}")
        except Exception as e:
            print(f"  Failed: {r.name} ({e})")

    await lk.aclose()
    print(f"\nDone. Deleted {len(rooms.rooms)} room(s).")


if __name__ == "__main__":
    asyncio.run(main())
