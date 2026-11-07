from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationRead(BaseModel):
    id: UUID
    notification_type: str
    category: str
    title: str
    body: str
    metadata: dict = Field(validation_alias="metadata_")
    action_label: str | None
    action_url: str | None
    occurred_at: datetime
    read_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationUpdate(BaseModel):
    is_read: bool


class NotificationList(BaseModel):
    items: list[NotificationRead]
    next_cursor: str | None


class NotificationUnreadCount(BaseModel):
    count: int = Field(ge=0)


class NotifyHubInAppRecipient(BaseModel):
    user_id: UUID


class NotifyHubInAppContent(BaseModel):
    data: dict = Field(default_factory=dict)
    action_label: str | None = Field(default=None, max_length=80)
    action_url: str | None = Field(default=None, max_length=500)


class NotifyHubInAppDelivery(BaseModel):
    delivery_id: str = Field(min_length=1, max_length=255)
    event_id: UUID
    workflow_key: str = Field(min_length=1, max_length=120)
    recipient: NotifyHubInAppRecipient
    occurred_at: datetime
    content: NotifyHubInAppContent
