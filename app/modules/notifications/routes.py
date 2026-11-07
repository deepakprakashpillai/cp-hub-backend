from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.api.deps import DBSession
from app.modules.auth.dependencies import CurrentUser
from app.modules.notifications.schemas import (
    NotificationList,
    NotificationRead,
    NotificationUnreadCount,
    NotificationUpdate,
    NotifyHubInAppDelivery,
)
from app.modules.notifications.service import NotificationService

router = APIRouter()
notify_hub_router = APIRouter()
Limit = Annotated[int, Query(ge=1, le=100)]


@router.get("", response_model=NotificationList)
async def list_notifications(
    session: DBSession,
    user: CurrentUser,
    state: str = Query("all", pattern="^(all|unread)$"),
    category: str | None = None,
    cursor: UUID | None = None,
    limit: Limit = 25,
) -> NotificationList:
    return await NotificationService(session).list_for_user(
        user.id, state=state, category=category, cursor=cursor, limit=limit
    )


@router.get("/unread-count", response_model=NotificationUnreadCount)
async def notification_unread_count(
    session: DBSession, user: CurrentUser
) -> NotificationUnreadCount:
    return NotificationUnreadCount(count=await NotificationService(session).unread_count(user.id))


@router.patch("/{notification_id}", response_model=NotificationRead)
async def update_notification(
    notification_id: UUID, body: NotificationUpdate, session: DBSession, user: CurrentUser
) -> NotificationRead:
    return await NotificationService(session).set_read(notification_id, user.id, body.is_read)


@router.post("/read-all", status_code=204)
async def mark_all_notifications_read(session: DBSession, user: CurrentUser) -> None:
    await NotificationService(session).mark_all_read(user.id)


@notify_hub_router.post("/in-app-deliveries", status_code=status.HTTP_204_NO_CONTENT)
async def receive_notify_hub_in_app_delivery(request: Request, session: DBSession) -> Response:
    """Persist a signed in-app delivery rendered and dispatched by Notify-Hub."""
    raw_body = await request.body()
    service = NotificationService(session)
    if not service.is_valid_notify_hub_signature(raw_body, request.headers.get("X-Hub-Signature")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")
    try:
        delivery = NotifyHubInAppDelivery.model_validate_json(raw_body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await service.record_notify_hub_in_app_delivery(delivery)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
