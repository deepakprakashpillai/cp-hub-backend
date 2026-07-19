from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_students() -> dict[str, str]:
    return {"module": "students"}
