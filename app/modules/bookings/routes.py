from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_bookings() -> dict[str, str]:
    return {"module": "bookings"}
