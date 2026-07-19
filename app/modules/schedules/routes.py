from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_schedules() -> dict[str, str]:
    return {"module": "schedules"}
