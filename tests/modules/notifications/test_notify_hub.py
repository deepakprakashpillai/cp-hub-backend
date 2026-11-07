import hashlib
import hmac

from app.core.config import settings
from app.modules.notifications.service import NotificationService


def test_notify_hub_signature_validation(monkeypatch) -> None:
    monkeypatch.setattr(settings, "notify_hub_webhook_secret", "test-secret")
    body = b'{"event_id":"example"}'
    signature = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

    assert NotificationService.is_valid_notify_hub_signature(body, f"sha256={signature}")
    assert not NotificationService.is_valid_notify_hub_signature(body, "sha256=invalid")
    assert not NotificationService.is_valid_notify_hub_signature(body, None)
