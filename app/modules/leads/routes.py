from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_leads() -> dict[str, str]:
    return {"module": "leads"}
