"""Automated parent notifications: service, triggers, dedupe and delivery rates."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from core import notifications
from core.models import (
    Attendance,
    Fee,
    NotificationLog,
    Payment,
    Profile,
    PublishStatus,
    Result,
    StudentFee,
)

LOGS_URL = "/api/notifications/logs/"


@pytest.fixture
def phone_parent(parent):
    profile = parent.profile
    profile.phone_number = "08031234567"
    profile.phone_verified = True
    profile.save()
    return parent


@pytest.fixture
def fee(session, term, school_class):
    return Fee.objects.create(
        session=session,
        term=term,
        class_level=school_class.level,
        amount=Decimal("45000.00"),
        description="Tuition and levies",
    )


@pytest.fixture
def student_fee(student, fee):
    return StudentFee.objects.create(student=student, fee=fee)


@pytest.fixture
def staff_client(db):
    user = User.objects.create_user("principal", password="Principal!2026", is_staff=True)
    Profile.objects.update_or_create(user=user, defaults={"role": Profile.TEACHER})
    client = APIClient()
    client.force_authenticate(user)
    return client


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
def test_notify_sends_and_records(phone_parent):
    log = notifications.notify(phone_parent, NotificationLog.ABSENCE, "Hello parent", {"x": 1})

    assert log is not None
    assert log.status == NotificationLog.SENT
    assert log.channel == NotificationLog.SMS
    assert log.external_id.startswith("mock-")
    assert log.payload["message"] == "Hello parent"
    assert log.payload["to"] == "08031234567"
    assert NotificationLog.objects.filter(pk=log.pk, status=NotificationLog.SENT).exists()


def test_whatsapp_is_used_when_enabled(settings, phone_parent):
    settings.WHATSAPP_ENABLED = True

    log = notifications.notify(phone_parent, NotificationLog.RESULT, "Results are out")

    assert log.channel == NotificationLog.WHATSAPP


def test_email_is_the_fallback(parent):
    log = notifications.notify(parent, NotificationLog.RESULT, "Results are out")

    assert log.channel == NotificationLog.EMAIL
    assert log.payload["to"] == "chioma@example.com"


def test_missing_contact_is_skipped(parent):
    profile = parent.profile
    profile.phone_number = ""
    profile.save()
    parent.email = ""
    parent.save()

    assert notifications.notify(parent, NotificationLog.RESULT, "Nobody home") is None
    assert NotificationLog.objects.count() == 0


def test_provider_failure_is_recorded_not_raised(monkeypatch, phone_parent):
    class BrokenProvider:
        def send(self, **kwargs):
            raise RuntimeError("gateway down")

    monkeypatch.setattr(notifications, "get_provider", lambda: BrokenProvider())

    log = notifications.notify(phone_parent, NotificationLog.ABSENCE, "Hello")

    assert log.status == NotificationLog.FAILED


# ---------------------------------------------------------------------------
# Absence alert
# ---------------------------------------------------------------------------
def test_absent_student_notifies_each_parent(student, classmate, school_class, phone_parent):
    today = timezone.localdate()
    for ward in (student, classmate):
        Attendance.objects.create(
            school_class=school_class, student=ward, date=today, status=Attendance.ABSENT
        )

    logs = NotificationLog.objects.filter(event_type=NotificationLog.ABSENCE)
    assert logs.count() == 2  # one message per absent ward
    messages = [log.payload["message"] for log in logs]
    assert any("Chidera Okafor" in message for message in messages)
    assert any("Emeka Nwosu" in message for message in messages)
    assert all("Please contact the school." in message for message in messages)


def test_absence_alert_is_not_duplicated(student, school_class, phone_parent):
    today = timezone.localdate()
    attendance = Attendance.objects.create(
        school_class=school_class, student=student, date=today, status=Attendance.ABSENT
    )
    attendance.save()

    assert NotificationLog.objects.filter(event_type=NotificationLog.ABSENCE).count() == 1


def test_present_student_is_not_alerted(student, school_class, phone_parent):
    Attendance.objects.create(
        school_class=school_class,
        student=student,
        date=timezone.localdate(),
        status=Attendance.PRESENT,
    )

    assert not NotificationLog.objects.filter(event_type=NotificationLog.ABSENCE).exists()


def test_absence_does_not_crash_without_a_phone(student, school_class, parent):
    parent.profile.phone_number = ""
    parent.profile.save()
    parent.email = ""
    parent.save()

    Attendance.objects.create(
        school_class=school_class,
        student=student,
        date=timezone.localdate(),
        status=Attendance.ABSENT,
    )

    assert not NotificationLog.objects.exists()


# ---------------------------------------------------------------------------
# Payment receipt
# ---------------------------------------------------------------------------
def test_successful_payment_sends_a_receipt(parent, student_fee, fee):
    payment = Payment.objects.create(
        parent=parent,
        student_fee=student_fee,
        amount=Decimal("20000.00"),
        reference="FEE-RECEIPT-1",
        status=Payment.SUCCESS,
    )

    log = NotificationLog.objects.get(event_type=NotificationLog.PAYMENT)
    message = log.payload["message"]
    assert "Receipt" in message
    assert "₦20,000.00" in message
    assert fee.term.name in message
    assert "Outstanding balance: ₦45,000.00" in message
    assert log.payload["payment_id"] == payment.pk


def test_receipt_shows_the_balance_after_part_payment(parent, student_fee):
    # The webhook credits the fee before saving the payment, which is what the
    # receipt reads; 30,000 paid + this 10,000 leaves 15,000 outstanding.
    student_fee.amount_paid = Decimal("30000.00")
    student_fee.save()

    Payment.objects.create(
        parent=parent,
        student_fee=student_fee,
        amount=Decimal("10000.00"),
        reference="FEE-RECEIPT-2",
        status=Payment.SUCCESS,
    )

    message = NotificationLog.objects.get(event_type=NotificationLog.PAYMENT).payload["message"]
    assert "Outstanding balance: ₦15,000.00" in message


def test_receipt_is_sent_once(parent, student_fee):
    payment = Payment.objects.create(
        parent=parent,
        student_fee=student_fee,
        amount=Decimal("5000.00"),
        reference="FEE-RECEIPT-3",
        status=Payment.SUCCESS,
    )
    payment.save()

    assert NotificationLog.objects.filter(event_type=NotificationLog.PAYMENT).count() == 1


def test_pending_payment_sends_nothing(parent, student_fee):
    Payment.objects.create(
        parent=parent,
        student_fee=student_fee,
        amount=Decimal("5000.00"),
        reference="FEE-PENDING-1",
    )

    assert not NotificationLog.objects.filter(event_type=NotificationLog.PAYMENT).exists()


# ---------------------------------------------------------------------------
# Result published
# ---------------------------------------------------------------------------
def make_result(student, subject, session, term, status=PublishStatus.PUBLISHED):
    return Result.objects.create(
        student=student,
        subject=subject,
        session=session,
        term=term,
        ca1=8,
        ca2=9,
        ca3=11,
        exam=40,
        status=status,
    )


def test_publishing_a_result_notifies_class_parents_once(parent, student, classmate, subject, session, term):
    make_result(student, subject, session, term)
    make_result(classmate, subject, session, term)

    logs = NotificationLog.objects.filter(event_type=NotificationLog.RESULT)
    assert logs.count() == 1  # one parent, two children, one announcement
    message = logs.first().payload["message"]
    assert "results for JSS 2A have been published" in message
    assert "Please log in to view." in message


def test_draft_results_are_not_announced(parent, student, subject, session, term):
    make_result(student, subject, session, term, status=PublishStatus.DRAFT)

    assert not NotificationLog.objects.filter(event_type=NotificationLog.RESULT).exists()


# ---------------------------------------------------------------------------
# Delivery dashboard
# ---------------------------------------------------------------------------
def test_logs_endpoint_is_staff_only(teacher_client, student_client):
    assert teacher_client.get(LOGS_URL).status_code == 403
    assert student_client.get(LOGS_URL).status_code == 403
    assert APIClient().get(LOGS_URL).status_code == 401


def test_logs_endpoint_reports_delivery_rates(staff_client, phone_parent):
    notifications.notify(phone_parent, NotificationLog.ABSENCE, "Sent message")
    NotificationLog.objects.create(
        recipient=phone_parent,
        channel=NotificationLog.SMS,
        event_type=NotificationLog.RESULT,
        status=NotificationLog.FAILED,
    )
    NotificationLog.objects.create(
        recipient=phone_parent,
        channel=NotificationLog.SMS,
        event_type=NotificationLog.RESULT,
        status=NotificationLog.PENDING,
    )

    response = staff_client.get(LOGS_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total"] == 3
    assert body["summary"]["sent"] == 1
    assert body["summary"]["failed"] == 1
    assert body["summary"]["pending"] == 1
    assert body["summary"]["delivery_rate"] == 33.3
    assert body["summary"]["by_channel"] == {"sms": 3}
    assert len(body["logs"]) == 3
    assert body["logs"][0]["recipient"] == "parent"


def test_logs_endpoint_filters(staff_client, phone_parent):
    notifications.notify(phone_parent, NotificationLog.ABSENCE, "Sent message")
    NotificationLog.objects.create(
        recipient=phone_parent,
        channel=NotificationLog.EMAIL,
        event_type=NotificationLog.RESULT,
        status=NotificationLog.FAILED,
    )

    body = staff_client.get(f"{LOGS_URL}?event_type=result_published").json()

    assert body["summary"]["total"] == 1
    assert body["logs"][0]["channel"] == NotificationLog.EMAIL


def test_notification_timestamp_is_recent(phone_parent):
    notifications.notify(phone_parent, NotificationLog.RESULT, "Recent")

    log = NotificationLog.objects.get()
    assert log.created_at >= timezone.now() - timedelta(minutes=1)
