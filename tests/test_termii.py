"""Termii provider tests use a fake urlopen; nothing makes a real network call."""

import json
import urllib.error

import pytest

from core.models import NotificationLog, Profile
from core.notifications import (
    TERMII_SMS_URL,
    TERMII_WHATSAPP_URL,
    TermiiDeliveryError,
    TermiiProvider,
    normalize_nigerian_phone,
    notify,
)


@pytest.fixture
def sms_parent(parent):
    profile = parent.profile
    profile.phone_number = "08031234567"
    profile.phone_verified = True
    profile.save()
    return parent


@pytest.mark.parametrize(
    ("phone", "expected"),
    [
        ("08031234567", "2348031234567"),
        ("+2348031234567", "2348031234567"),
        ("2348031234567", "2348031234567"),
        ("  +234 803 123 4567  ", "2348031234567"),
        ("07012345678", "2347012345678"),
        ("09012345678", "2349012345678"),
    ],
)
def test_normalize_nigerian_phone_variants(phone, expected):
    assert normalize_nigerian_phone(phone) == expected


@pytest.mark.parametrize("phone", ["+14155552671", "0803123456", "12345678901", "abc"])
def test_rejects_non_nigerian_or_invalid_numbers(phone):
    with pytest.raises(TermiiDeliveryError):
        normalize_nigerian_phone(phone)


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return self.body


def test_successful_termii_sms_uses_dnd_and_records_message_id(settings, sms_parent, monkeypatch):
    settings.TERMII_API_KEY = "test-termii-key"
    settings.TERMII_SENDER_ID = "SchoolTest"
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data)
        return FakeResponse(b'{"message_id":"termii-msg-123","balance":42}')

    monkeypatch.setattr("core.notifications.urllib.request.urlopen", fake_urlopen)

    log = notify(sms_parent, NotificationLog.ABSENCE, "Student was absent")

    assert log.status == NotificationLog.SENT
    assert log.external_id == "termii-msg-123"
    assert captured["url"] == TERMII_SMS_URL
    assert captured["timeout"] == 10
    assert captured["body"] == {
        "api_key": "test-termii-key",
        "to": "2348031234567",
        "from": "SchoolTest",
        "sms": "Student was absent",
        "type": "plain",
        "channel": "dnd",
        "api": "json",
    }
    assert log.payload["to"] == "08031234567"


def test_whatsapp_uses_the_configured_template_channel(settings, sms_parent, monkeypatch):
    settings.TERMII_API_KEY = "test-termii-key"
    settings.WHATSAPP_ENABLED = True
    settings.TERMII_WHATSAPP_TEMPLATE_ID = "template-123"
    settings.TERMII_WHATSAPP_DEVICE_ID = "device-456"
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        return FakeResponse(b'{"message_id":"whatsapp-123"}')

    monkeypatch.setattr("core.notifications.urllib.request.urlopen", fake_urlopen)

    log = notify(sms_parent, NotificationLog.RESULT, "Results are published")

    assert log.status == NotificationLog.SENT
    assert captured["url"] == TERMII_WHATSAPP_URL
    assert captured["body"] == {
        "api_key": "test-termii-key",
        "to": "2348031234567",
        "from": "SchoolApp",
        "sms": "Results are published",
        "type": "template",
        "channel": "whatsapp",
        "api": "json",
        "template_id": "template-123",
        "device_id": "device-456",
    }


def test_whatsapp_without_approved_configuration_is_failed(settings, sms_parent, monkeypatch):
    settings.TERMII_API_KEY = "test-termii-key"
    settings.WHATSAPP_ENABLED = True
    called = False

    def no_network(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("WhatsApp cannot be sent without approved template and device")

    monkeypatch.setattr("core.notifications.urllib.request.urlopen", no_network)

    log = notify(sms_parent, NotificationLog.RESULT, "Results are published")

    assert log.status == NotificationLog.FAILED
    assert log.payload["provider_error"]["code"] == "whatsapp_template_not_configured"
    assert called is False


def test_http_success_missing_message_id_is_failed(settings, sms_parent, monkeypatch):
    settings.TERMII_API_KEY = "test-termii-key"
    monkeypatch.setattr(
        "core.notifications.urllib.request.urlopen",
        lambda request, timeout: FakeResponse(b'{"balance":42}'),
    )

    log = notify(sms_parent, NotificationLog.ABSENCE, "Absent")

    assert log.status == NotificationLog.FAILED
    assert log.payload["provider_error"]["code"] == "missing_message_id"


def test_timeout_is_failed_and_does_not_raise(settings, sms_parent, monkeypatch):
    settings.TERMII_API_KEY = "test-termii-key"

    def timeout(request, timeout):
        assert timeout == 10
        raise TimeoutError("Termii timed out")

    monkeypatch.setattr("core.notifications.urllib.request.urlopen", timeout)

    log = notify(sms_parent, NotificationLog.ABSENCE, "Absent")

    assert log.status == NotificationLog.FAILED
    assert log.payload["provider_error"]["code"] == "network_error"
    assert log.payload["provider_status_code"] == 504


def test_http_failure_is_recorded(settings, sms_parent, monkeypatch):
    settings.TERMII_API_KEY = "test-termii-key"

    def rejected(request, timeout):
        raise urllib.error.HTTPError(
            TERMII_SMS_URL,
            429,
            "rate limited",
            {},
            __import__("io").BytesIO(b'{"message":"rate limit"}'),
        )

    monkeypatch.setattr("core.notifications.urllib.request.urlopen", rejected)

    log = notify(sms_parent, NotificationLog.ABSENCE, "Absent")

    assert log.status == NotificationLog.FAILED
    assert log.payload["provider_error"]["http_status"] == 429
    assert log.payload["provider_error"]["body"]["message"] == "rate limit"


def test_missing_key_records_failure(settings, sms_parent):
    settings.TERMII_API_KEY = ""

    log = notify(sms_parent, NotificationLog.ABSENCE, "Absent")

    assert log.status == NotificationLog.FAILED
    assert log.payload["provider_error"]["code"] == "missing_api_key"
    assert log.payload["provider_status_code"] == 503


def test_non_nigerian_number_is_logged_failed_without_network(settings, sms_parent, monkeypatch):
    settings.TERMII_API_KEY = "test-termii-key"
    sms_parent.profile.phone_number = "+14155552671"
    sms_parent.profile.save()
    called = False

    def no_network(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("invalid destination must not be sent")

    monkeypatch.setattr("core.notifications.urllib.request.urlopen", no_network)

    log = notify(sms_parent, NotificationLog.ABSENCE, "Absent")

    assert log.status == NotificationLog.FAILED
    assert log.payload["provider_error"]["code"] == "invalid_phone"
    assert called is False


def test_provider_directly_raises_for_missing_api_key(settings):
    settings.TERMII_API_KEY = ""
    with pytest.raises(TermiiDeliveryError) as error:
        TermiiProvider().send(channel=NotificationLog.SMS, recipient="08031234567", message="Hi")
    assert error.value.status_code == 503


def test_sms_parent_fixture_is_parent(sms_parent):
    assert sms_parent.profile.role == Profile.PARENT
