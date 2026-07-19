from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_teachers() -> dict[str, str]:
    return {"module": "teachers"}
