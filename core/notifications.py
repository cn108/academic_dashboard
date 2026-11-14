"""Automated parent notifications.

Every message goes through one place (:func:`notify`) so swapping the mock
provider for Termii or Twilio later is a one-function change. Triggers are
Django signals, and they never raise: a missing phone number or a failing
provider must not break the attendance save, payment webhook or result publish
that caused them.
"""

import logging
import uuid

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Attendance, NotificationLog, ParentStudentLink, Payment, Result

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
class MockProvider:
    """Logs the message instead of sending it. Safe for demos and tests."""

    name = "mock"

    def send(self, *, channel: str, recipient: str, message: str) -> str:
        logger.info("[%s mock] to %s: %s", channel, recipient, message)
        return f"mock-{uuid.uuid4().hex[:12]}"


def get_provider():
    """The provider every notification is delivered through.

    Replace the body with ``TermiiProvider()`` (or Twilio) once
    ``TERMII_API_KEY`` is provisioned; the rest of this module only relies on
    ``provider.send(channel=..., recipient=..., message=...)``.
    """
    return MockProvider()


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
def channel_for(user) -> str:
    """WhatsApp when enabled, SMS otherwise, email as the last resort."""
    profile = getattr(user, "profile", None)
    if profile is not None and profile.phone_number:
        return NotificationLog.WHATSAPP if settings.WHATSAPP_ENABLED else NotificationLog.SMS
    if user.email:
        return NotificationLog.EMAIL
    return ""


def notify(user, event_type: str, message: str, payload: dict | None = None):
    """Deliver one message and record it. Returns None when we cannot reach them.

    Failures are captured on the log row, never raised to the caller.
    """
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
        external_id = get_provider().send(channel=channel, recipient=destination, message=message)
    except Exception:  # noqa: BLE001 - a provider outage must not break the request
        logger.exception("Notification %s failed for %s", log.pk, user.get_username())
        log.status = NotificationLog.FAILED
        log.save(update_fields=["status"])
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
