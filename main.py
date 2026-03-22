import asyncio
import os
import sys
from pathlib import Path

# Load .env file if it exists (for local development)
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)
    print("[Config] Loaded .env file")

# Validate required environment variables
required_vars = ["DISCORD_BOT_TOKEN", "DISCORD_CLIENT_ID", "DATABASE_URL"]
missing = [v for v in required_vars if not os.environ.get(v)]
if missing:
    print(f"[Error] Missing required environment variables: {', '.join(missing)}")
    print("Copy .env.example to .env and fill in your values.")
    sys.exit(1)

# Add project root to Python path so imports work correctly
sys.path.insert(0, str(Path(__file__).parent))

from bot import LeaderboardBot


async def main():
    bot = LeaderboardBot()
    async with bot:
        await bot.start(os.environ["DISCORD_BOT_TOKEN"])


if __name__ == "__main__":
    asyncio.run(main())
