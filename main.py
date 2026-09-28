import asyncio
import logging
from config import settings
from database import init_db

async def main() -> None:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    await init_db()
    logging.getLogger(__name__).info("Baraholka VK foundation initialized.")

if __name__ == "__main__":
    asyncio.run(main())
