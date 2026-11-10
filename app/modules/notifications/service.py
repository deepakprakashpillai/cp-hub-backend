from __future__ import annotations

import hashlib
import hmac
from datetime import timedelta
from uuid import UUID

import httpx
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.notifications.models import Notification, NotificationOutboxEvent
from app.modules.notifications.schemas import NotificationList, NotifyHubInAppDelivery
from app.modules.users.models import User
from app.shared.enums import UserRole
from app.shared.utils import utc_now


class NotificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def emit(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        dedupe_key: str,
        payload: dict,
        actor_user_id: UUID | None = None,
    ) -> NotificationOutboxEvent:
        existing = await self.session.scalar(
            select(NotificationOutboxEvent).where(NotificationOutboxEvent.dedupe_key == dedupe_key)
        )
        if existing is not None:
            return existing
        event = NotificationOutboxEvent(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            dedupe_key=dedupe_key,
            payload=payload,
            actor_user_id=actor_user_id,
        )
        self.session.add(event)
        return event

    async def emit_to_users(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        dedupe_key: str,
        recipient_user_ids: list[UUID],
        title: str,
        body: str,
        category: str,
        priority: str,
        action_url: str | None,
        action_label: str = "View",
        data: dict | None = None,
        actor_user_id: UUID | None = None,
        include_admins: bool = False,
    ) -> NotificationOutboxEvent:
        recipients = set(recipient_user_ids)
        if include_admins:
            admins = await self.session.scalars(
                select(User.id).where(
                    (User.role == UserRole.ADMIN) | (User.additional_role == UserRole.ADMIN),
                    User.is_active.is_(True),
                )
            )
            recipients.update(admins)
            recipients.discard(actor_user_id)
        return await self.emit(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            dedupe_key=dedupe_key,
            actor_user_id=actor_user_id,
            payload={
                "recipients": [str(recipient) for recipient in recipients],
                "title": title,
                "body": body,
                "category": category,
                "priority": priority,
                "action_url": action_url,
                "action_label": action_label,
                "data": {
                    "event_type": event_type,
                    "entity": {"type": aggregate_type, "id": str(aggregate_id)},
                    **(data or {}),
                },
            },
        )

    async def emit_to_audiences(
        self,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: UUID,
        dedupe_key: str,
        audiences: dict[str, list[UUID]],
        category: str,
        priority: str,
        data: dict | None = None,
        actor_user_id: UUID | None = None,
        include_admins: bool = False,
    ) -> NotificationOutboxEvent:
        resolved = {key: set(user_ids) for key, user_ids in audiences.items()}
        if include_admins:
            admins = await self.session.scalars(
                select(User.id).where(
                    (User.role == UserRole.ADMIN) | (User.additional_role == UserRole.ADMIN),
                    User.is_active.is_(True),
                )
            )
            resolved.setdefault("admin", set()).update(admins)
            resolved["admin"].discard(actor_user_id)
        return await self.emit(
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            dedupe_key=dedupe_key,
            actor_user_id=actor_user_id,
            payload={
                "audiences": {
                    key: [str(user_id) for user_id in user_ids]
                    for key, user_ids in resolved.items()
                    if user_ids
                },
                "category": category,
                "priority": priority,
                "data": {
                    "event_type": event_type,
                    "entity": {"type": aggregate_type, "id": str(aggregate_id)},
                    **(data or {}),
                },
            },
        )

    async def list_for_user(
        self, user_id: UUID, *, state: str, category: str | None, cursor: UUID | None, limit: int
    ) -> NotificationList:
        statement = select(Notification).where(Notification.recipient_user_id == user_id)
        if state == "unread":
            statement = statement.where(Notification.read_at.is_(None))
        if category:
            statement = statement.where(Notification.category == category)
        if cursor:
            cursor_row = await self.session.get(Notification, cursor)
            if cursor_row and cursor_row.recipient_user_id == user_id:
                statement = statement.where(
                    or_(
                        Notification.created_at < cursor_row.created_at,
                        and_(
                            Notification.created_at == cursor_row.created_at,
                            Notification.id < cursor_row.id,
                        ),
                    )
                )
        statement = statement.order_by(
            Notification.created_at.desc(), Notification.id.desc()
        ).limit(limit + 1)
        rows = list(await self.session.scalars(statement))
        next_cursor = str(rows[limit].id) if len(rows) > limit else None
        return NotificationList(items=rows[:limit], next_cursor=next_cursor)

    async def unread_count(self, user_id: UUID) -> int:
        return (
            await self.session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.recipient_user_id == user_id, Notification.read_at.is_(None))
            )
            or 0
        )

    async def set_read(self, notification_id: UUID, user_id: UUID, is_read: bool) -> Notification:
        notification = await self.session.scalar(
            select(Notification).where(
                Notification.id == notification_id, Notification.recipient_user_id == user_id
            )
        )
        if notification is None:
            from app.core.exceptions import NotFoundError

            raise NotFoundError("Notification not found")
        notification.read_at = utc_now() if is_read else None
        await self.session.commit()
        await self.session.refresh(notification)
        return notification

    async def mark_all_read(self, user_id: UUID) -> None:
        rows = await self.session.scalars(
            select(Notification).where(
                Notification.recipient_user_id == user_id,
                Notification.read_at.is_(None),
            )
        )
        now = utc_now()
        for notification in rows:
            notification.read_at = now
        await self.session.commit()

    async def cleanup_read(self) -> int:
        cutoff = utc_now() - timedelta(days=183)
        rows = await self.session.scalars(
            select(Notification).where(
                Notification.read_at.is_not(None), Notification.created_at < cutoff
            )
        )
        notifications = list(rows)
        for notification in notifications:
            await self.session.delete(notification)
        await self.session.commit()
        return len(notifications)

    async def process_pending(self, limit: int = 100) -> int:
        """Send durable CP Hub events to Notify-Hub. Safe to run from multiple workers."""
        now = utc_now()
        events = list(
            await self.session.scalars(
                select(NotificationOutboxEvent)
                .where(
                    NotificationOutboxEvent.processed_at.is_(None),
                    or_(
                        NotificationOutboxEvent.next_attempt_at.is_(None),
                        NotificationOutboxEvent.next_attempt_at <= now,
                    ),
                )
                .order_by(NotificationOutboxEvent.occurred_at)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
        )
        processed = 0
        for event in events:
            try:
                await self._send_to_notify_hub(event)
                event.processed_at = now
                event.last_error = None
                processed += 1
            except Exception as exc:  # pragma: no cover - defensive worker boundary
                event.attempts += 1
                event.last_error = str(exc)[:2000]
                event.next_attempt_at = now + timedelta(
                    minutes=min(60, 2 ** min(event.attempts, 6))
                )
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
        return processed

    async def _send_to_notify_hub(self, event: NotificationOutboxEvent) -> None:
        if not settings.notify_hub_base_url or not settings.notify_hub_api_key:
            raise RuntimeError("Notify-Hub is not configured")
        audience_ids = event.payload.get("audiences")
        recipients_by_audience = audience_ids or {"default": event.payload.get("recipients", [])}
        recipient_ids = list(
            dict.fromkeys(
                user_id for user_ids in recipients_by_audience.values() for user_id in user_ids
            )
        )
        if not recipient_ids:
            raise ValueError("Notification event has no recipients")
        recipients = list(
            await self.session.scalars(select(User).where(User.id.in_(recipient_ids)))
        )
        if len(recipients) != len(recipient_ids):
            raise ValueError("Notification event contains an unknown recipient")
        priority = {"high": "high", "low": "low"}.get(event.payload.get("priority"), "default")
        recipient_data = {
            str(user.id): {
                "user_id": str(user.id),
                "email": user.email,
                "phone": user.phone,
                "data": {"full_name": user.full_name},
            }
            for user in recipients
        }
        body = {
            "event_id": str(event.id),
            "workflow": event.event_type,
            **(
                {
                    "audiences": {
                        key: [recipient_data[str(user_id)] for user_id in user_ids]
                        for key, user_ids in audience_ids.items()
                    }
                }
                if audience_ids
                else {"recipients": list(recipient_data.values())}
            ),
            "data": {
                **event.payload.get("data", {}),
                "category": event.payload.get("category", "updates"),
                "priority": event.payload.get("priority", "medium"),
                "aggregate_type": event.aggregate_type,
                "aggregate_id": str(event.aggregate_id),
            },
            "priority": priority,
            "occurred_at": event.occurred_at.isoformat(),
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{settings.notify_hub_base_url.rstrip('/')}/v1/events",
                headers={"Authorization": f"Bearer {settings.notify_hub_api_key}"},
                json=body,
            )
        response.raise_for_status()

    @staticmethod
    def is_valid_notify_hub_signature(raw_body: bytes, signature: str | None) -> bool:
        secret = settings.notify_hub_webhook_secret
        if not secret or not signature or not signature.startswith("sha256="):
            return False
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature.removeprefix("sha256="), expected)

    async def record_notify_hub_in_app_delivery(
        self, delivery: NotifyHubInAppDelivery
    ) -> Notification:
        event = await self.session.get(NotificationOutboxEvent, delivery.event_id)
        if event is None:
            from app.core.exceptions import NotFoundError

            raise NotFoundError("Notify-Hub delivery does not match a CP Hub event")
        existing = await self.session.scalar(
            select(Notification).where(
                Notification.recipient_user_id == delivery.recipient.user_id,
                Notification.outbox_event_id == event.id,
            )
        )
        if existing is not None:
            return existing
        action_url = delivery.content.action_url
        if action_url and (not action_url.startswith("/") or action_url.startswith("//")):
            action_url = None
        notification = Notification(
            recipient_user_id=delivery.recipient.user_id,
            outbox_event_id=event.id,
            notification_type=delivery.workflow_key,
            category=event.payload.get("category", "updates"),
            priority=event.payload.get("priority", "medium"),
            title="",
            body="",
            metadata_=delivery.content.data,
            action_label=delivery.content.action_label,
            action_url=action_url,
            occurred_at=delivery.occurred_at,
        )
        self.session.add(notification)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.session.scalar(
                select(Notification).where(
                    Notification.recipient_user_id == delivery.recipient.user_id,
                    Notification.outbox_event_id == event.id,
                )
            )
            if existing is None:  # pragma: no cover - defensive concurrency boundary
                raise
            return existing
        await self.session.refresh(notification)
        return notification
