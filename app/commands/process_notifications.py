import asyncio

from app.db.session import async_session
from app.modules.notifications.service import NotificationService


async def run() -> None:
    async with async_session() as session:
        processed = await NotificationService(session).process_pending()
    print(f"Notification events sent to Notify-Hub: {processed}")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
