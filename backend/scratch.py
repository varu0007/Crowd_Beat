import asyncio
from app.services.spotify_service import get_playlist_tracks
import os

async def main():
    token = os.environ.get("SPOTIFY_TOKEN")
    if not token: print("no token")
    # Actually I can't easily run this without a valid Spotify token.
    pass

asyncio.run(main())
