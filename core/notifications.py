"""Automated parent notifications and provider adapters.

Every message goes through :func:`notify`. The production adapter uses Termii;
MockProvider remains available for tests and local development. Signal handlers
never raise into an attendance save, Paystack webhook or result publish.
"""

import json
import logging
import urllib.error
import urllib.request
import uuid

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Attendance, NotificationLog, ParentStudentLink, Payment, Result

logger = logging.getLogger(__name__)
TERMII_SMS_URL = "https://api.ng.termii.com/api/sms/send"
TERMII_WHATSAPP_URL = "https://api.ng.termii.com/api/message/send"
TERMII_TIMEOUT_SECONDS = 10


class TermiiDeliveryError(Exception):
    """A Termii configuration, validation, HTTP or network failure."""

    def __init__(self, message: str, *, details: dict | None = None, status_code: int = 502):
        super().__init__(message)
        self.details = details or {"message": message}
        self.status_code = status_code


def normalize_nigerian_phone(phone: str) -> str:
    """Normalize a Nigerian mobile number to 234XXXXXXXXXX.

    Accepts local ``0803…``, international ``+234803…`` and international
    without plus ``234803…``. Other countries, bad lengths and malformed values
    are rejected before they can be sent to the provider.
    """
    raw = str(phone).strip()
    if not raw or any(character not in "+-() 0123456789" for character in raw):
        raise TermiiDeliveryError(
            "Enter a valid Nigerian mobile number.",
            details={"code": "invalid_phone", "phone": raw},
            status_code=400,
        )
    digits = "".join(character for character in raw if character.isdigit())
    if digits.startswith("234"):
        national = digits[3:]
    elif digits.startswith("0"):
        national = digits[1:]
    else:
        raise TermiiDeliveryError(
            "Only Nigerian phone numbers are supported.",
            details={"code": "invalid_phone", "phone": str(phone)},
            status_code=400,
        )

    if len(national) != 10 or national[0] not in "789":
        raise TermiiDeliveryError(
            "Enter a valid Nigerian mobile number.",
            details={"code": "invalid_phone", "phone": str(phone)},
            status_code=400,
        )
    return f"234{national}"


class MockProvider:
    """Logs the message instead of sending it. Useful for tests and demos."""

    name = "mock"

    def send(self, *, channel: str, recipient: str, message: str) -> str:
        logger.info("[%s mock] to %s: %s", channel, recipient, message)
        return f"mock-{uuid.uuid4().hex[:12]}"


class TermiiProvider:
    """Termii transactional SMS and opt-in WhatsApp template adapter."""

    name = "termii"

    def send(self, *, channel: str, recipient: str, message: str) -> str:
        api_key = settings.TERMII_API_KEY
        if not api_key:
            raise TermiiDeliveryError(
                "Termii is not configured. Add TERMII_API_KEY before sending notifications.",
                details={"code": "missing_api_key", "message": "TERMII_API_KEY is empty."},
                status_code=503,
            )

        phone = normalize_nigerian_phone(recipient)
        is_whatsapp = channel == NotificationLog.WHATSAPP
        endpoint = TERMII_WHATSAPP_URL if is_whatsapp else TERMII_SMS_URL
        if is_whatsapp:
            template_id = settings.TERMII_WHATSAPP_TEMPLATE_ID
            device_id = settings.TERMII_WHATSAPP_DEVICE_ID
            if not template_id or not device_id:
                raise TermiiDeliveryError(
                    "WhatsApp requires an approved template and configured device.",
                    details={
                        "code": "whatsapp_template_not_configured",
                        "message": (
                            "Set TERMII_WHATSAPP_TEMPLATE_ID and TERMII_WHATSAPP_DEVICE_ID after approval."
                        ),
                    },
                    status_code=503,
                )
            # The configured template and device must be pre-approved with Termii.
            body = {
                "api_key": api_key,
                "to": phone,
                "from": settings.TERMII_SENDER_ID,
                "sms": message,
                "type": "template",
                "channel": "whatsapp",
                "api": "json",
                "template_id": template_id,
                "device_id": device_id,
            }
        else:
            # Nigerian school alerts are transactional; DND is mandatory here.
            body = {
                "api_key": api_key,
                "to": phone,
                "from": settings.TERMII_SENDER_ID,
                "sms": message,
                "type": "plain",
                "channel": "dnd",
                "api": "json",
            }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=TERMII_TIMEOUT_SECONDS) as response:
                response_body = response.read()
                if response.status != 200:
                    raise TermiiDeliveryError(
                        f"Termii returned HTTP {response.status}.",
                        details={"http_status": response.status, "body": _decode_body(response_body)},
                        status_code=502,
                    )
        except urllib.error.HTTPError as error:
            response_body = error.read()
            raise TermiiDeliveryError(
                f"Termii returned HTTP {error.code}.",
                details={"http_status": error.code, "body": _decode_body(response_body)},
                status_code=502,
            ) from error
        except (TimeoutError, urllib.error.URLError) as error:
            reason = getattr(error, "reason", error)
            raise TermiiDeliveryError(
                "Termii request timed out or could not reach the service.",
                details={"code": "network_error", "message": str(reason)},
                status_code=504,
            ) from error

        try:
            result = json.loads(response_body or b"{}")
        except (ValueError, UnicodeDecodeError) as error:
            raise TermiiDeliveryError(
                "Termii returned an invalid JSON response.",
                details={"code": "invalid_response", "body": response_body.decode(errors="replace")},
                status_code=502,
            ) from error

        message_id = result.get("message_id") if isinstance(result, dict) else None
        if not message_id:
            raise TermiiDeliveryError(
                "Termii did not return a message_id.",
                details={"code": "missing_message_id", "response": result},
                status_code=502,
            )
        return str(message_id)


def _decode_body(body: bytes) -> dict | str:
    try:
        decoded = json.loads(body or b"{}")
        return decoded if isinstance(decoded, dict) else str(decoded)
    except (ValueError, UnicodeDecodeError):
        return body.decode(errors="replace")


def get_provider():
    """Return the production provider; inject MockProvider in tests as needed."""
    return TermiiProvider()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
def channel_for(user) -> str:
    """WhatsApp when enabled, SMS otherwise, email as the last resort."""
    profile = getattr(user, "profile", None)
    if profile is not None and profile.phone_number and profile.phone_verified:
        return NotificationLog.WHATSAPP if settings.WHATSAPP_ENABLED else NotificationLog.SMS
    if user.email:
        return NotificationLog.EMAIL
    return ""


def notify(user, event_type: str, message: str, payload: dict | None = None):
    """Deliver one message and record it. Provider failures never escape."""
    channel = channel_for(user)
    if not channel:
        logger.info(
            "No phone number or email for %s; skipping %s notification",
            user.get_username(),
            event_type,
        )
        return None

    profile = getattr(user, "profile", None)
    destination = profile.phone_number if profile and profile.phone_number else user.email
    log = NotificationLog.objects.create(
        recipient=user,
        channel=channel,
        event_type=event_type,
        payload={**(payload or {}), "message": message, "to": destination},
        status=NotificationLog.PENDING,
    )

    try:
        # This phase implements Termii SMS/WhatsApp. Keep the existing email
        # fallback on its mock adapter until an email gateway is requested.
        provider = MockProvider() if channel == NotificationLog.EMAIL else get_provider()
        external_id = provider.send(channel=channel, recipient=destination, message=message)
    except Exception as error:  # noqa: BLE001 - notifications must not break the caller
        logger.exception("Notification %s failed for %s", log.pk, user.get_username())
        log.status = NotificationLog.FAILED
        provider_details = getattr(error, "details", None)
        log.payload = {
            **log.payload,
            "provider_error": provider_details or {"message": str(error)},
            "provider_status_code": getattr(error, "status_code", None),
        }
        log.save(update_fields=["status", "payload"])
        return log

    log.status = NotificationLog.SENT
    log.external_id = external_id
    log.save(update_fields=["status", "external_id"])
    return log


def display_name(user) -> str:
    return user.get_full_name() or user.username


def money(amount) -> str:
    return f"₦{amount:,.2f}"


def linked_parents(student):
    return [
        link.parent
        for link in ParentStudentLink.objects.filter(student=student).select_related("parent__profile")
    ]


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------
@receiver(post_save, sender=Attendance)
def notify_absence(sender, instance, **kwargs):
    """A student marked absent today tells every linked parent."""
    if instance.status != Attendance.ABSENT:
        return

    try:
        today = instance.date or timezone.localdate()
        for parent in linked_parents(instance.student):
            already_sent = NotificationLog.objects.filter(
                recipient=parent,
                event_type=NotificationLog.ABSENCE,
                payload__student_id=instance.student_id,
                payload__date=today.isoformat(),
            ).exists()
            if already_sent:
                continue
            message = (
                f"Dear Parent, {display_name(instance.student)} was marked absent today, "
                f"{today:%d %b %Y}. Please contact the school."
            )
            notify(
                parent,
                NotificationLog.ABSENCE,
                message,
                {
                    "student_id": instance.student_id,
                    "class_id": instance.school_class_id,
                    "date": today.isoformat(),
                },
            )
    except Exception:  # noqa: BLE001
        logger.exception("Absence notification failed for attendance %s", instance.pk)


@receiver(post_save, sender=Payment)
def notify_payment_receipt(sender, instance, **kwargs):
    """A successful Paystack payment sends the paying parent a receipt."""
    if instance.status != Payment.SUCCESS:
        return

    try:
        if NotificationLog.objects.filter(
            event_type=NotificationLog.PAYMENT, payload__payment_id=instance.pk
        ).exists():
            return

        student_fee = instance.student_fee
        fee = student_fee.fee
        message = (
            f"Receipt: We have received {money(instance.amount)} for "
            f"{display_name(student_fee.student)}'s {fee.term.name} fees. "
            f"Outstanding balance: {money(student_fee.balance)}."
        )
        notify(
            instance.parent,
            NotificationLog.PAYMENT,
            message,
            {
                "payment_id": instance.pk,
                "student_id": student_fee.student_id,
                "reference": instance.reference,
                "amount": str(instance.amount),
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception("Payment receipt failed for payment %s", instance.pk)


@receiver(post_save, sender=Result)
def notify_result_published(sender, instance, **kwargs):
    """Publishing a result tells the class's parents once per term."""
    if instance.status != "published":
        return

    try:
        school_class = instance.subject.school_class
        if school_class is None:
            return

        links = ParentStudentLink.objects.filter(student__profile__school_class=school_class).select_related(
            "parent__profile"
        )

        seen: set[int] = set()
        for link in links:
            parent = link.parent
            if parent.pk in seen:
                continue
            seen.add(parent.pk)

            already_sent = NotificationLog.objects.filter(
                recipient=parent,
                event_type=NotificationLog.RESULT,
                payload__class_id=school_class.pk,
                payload__term_id=instance.term_id,
            ).exists()
            if already_sent:
                continue

            message = (
                f"Dear Parent, {instance.term.name} results for {school_class.name} "
                "have been published. Please log in to view."
            )
            notify(
                parent,
                NotificationLog.RESULT,
                message,
                {
                    "class_id": school_class.pk,
                    "term_id": instance.term_id,
                    "session_id": instance.session_id,
                },
            )
    except Exception:  # noqa: BLE001
        logger.exception("Result notification failed for result %s", instance.pk)
