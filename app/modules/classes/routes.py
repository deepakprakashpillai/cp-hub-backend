from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_classes() -> dict[str, str]:
    return {"module": "classes"}
