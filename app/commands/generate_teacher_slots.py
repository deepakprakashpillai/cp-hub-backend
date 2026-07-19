import asyncio

from app.db.session import async_session
from app.modules.schedules.slot_generation import sync_teacher_availability_slots


async def run() -> None:
    async with async_session() as session:
        result = await sync_teacher_availability_slots(session)

    print(
        "Teacher slot generation complete: "
        f"rules_checked={result.rules_checked}, "
        f"slots_created={result.slots_created}, "
        f"slots_cancelled={result.slots_cancelled}, "
        f"slots_skipped={result.slots_skipped}"
    )


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
