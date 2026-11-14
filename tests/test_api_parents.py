"""Parent portal: ward scoping, fee balances and payment initialisation."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import (
    Attendance,
    Fee,
    Payment,
    PublishStatus,
    Result,
    StudentFee,
)


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
def bus_fee(session, term, school_class):
    return Fee.objects.create(
        session=session,
        term=term,
        class_level=school_class.level,
        amount=Decimal("12000.00"),
        description="Bus service",
    )


def make_result(student, subject, session, term, exam, status=PublishStatus.PUBLISHED):
    return Result.objects.create(
        student=student,
        subject=subject,
        session=session,
        term=term,
        ca1=10,
        ca2=10,
        ca3=20,
        exam=exam,
        status=status,
    )


def student_fee(student, fee):
    row = StudentFee.objects.create(student=student, fee=fee)
    return row


# ---------------------------------------------------------------------------
# Wards
# ---------------------------------------------------------------------------
def test_wards_lists_only_linked_children(parent_client, student, classmate, outsider):
    response = parent_client.get("/api/parent/wards/")

    assert response.status_code == 200
    ids = {ward["id"] for ward in response.json()["wards"]}
    assert ids == {student.pk, classmate.pk}
    assert outsider.pk not in ids


def test_ward_average_ignores_drafts(parent_client, student, subject, school_class, teacher, session, term):
    from core.models import Subject

    draft_subject = Subject.objects.create(
        name="English Language", school_class=school_class, teacher=teacher
    )
    make_result(student, subject, session, term, exam=50)  # total 90
    make_result(student, draft_subject, session, term, exam=0, status=PublishStatus.DRAFT)

    response = parent_client.get("/api/parent/wards/")

    ward = next(row for row in response.json()["wards"] if row["id"] == student.pk)
    assert ward["subjects_count"] == 1
    assert ward["average"] == 90.0


def test_ward_attendance_rate(parent_client, student, school_class):
    today = timezone.localdate()
    for offset, status in ((0, Attendance.PRESENT), (1, Attendance.ABSENT), (2, Attendance.LATE)):
        Attendance.objects.create(
            school_class=school_class,
            student=student,
            date=today - timedelta(days=offset),
            status=status,
        )

    response = parent_client.get("/api/parent/wards/")

    ward = next(row for row in response.json()["wards"] if row["id"] == student.pk)
    assert ward["attendance_days"] == 3
    assert ward["attendance_rate"] == 67


def test_teacher_cannot_use_parent_portal(teacher_client):
    assert teacher_client.get("/api/parent/wards/").status_code == 403
    assert teacher_client.get("/api/parent/fees/").status_code == 403


def test_student_cannot_use_parent_portal(student_client):
    assert student_client.get("/api/parent/wards/").status_code == 403
    assert student_client.get("/api/parent/payments/").status_code == 403


# ---------------------------------------------------------------------------
# Fees
# ---------------------------------------------------------------------------
def test_fees_are_created_for_each_ward(parent_client, student, classmate, fee):
    response = parent_client.get("/api/parent/fees/")

    assert response.status_code == 200
    body = response.json()
    assert {row["student"] for row in body["fees"]} == {student.pk, classmate.pk}
    assert body["totals"]["amount"] == "90000.00"
    assert body["totals"]["balance"] == "90000.00"
    assert StudentFee.objects.filter(fee=fee).count() == 2


def test_fees_ignore_other_class_levels(parent_client, session, term, fee):
    Fee.objects.create(
        session=session,
        term=term,
        class_level="JSS 1",
        amount=Decimal("40000.00"),
        description="Tuition and levies",
    )

    body = parent_client.get("/api/parent/fees/").json()

    assert len(body["fees"]) == 2
    assert {row["description"] for row in body["fees"]} == {"Tuition and levies"}


def test_part_payment_marks_the_fee_partial(parent_client, student, fee):
    row = student_fee(student, fee)
    row.amount_paid = Decimal("20000.00")
    row.save()

    body = parent_client.get("/api/parent/fees/").json()

    mine = next(entry for entry in body["fees"] if entry["student"] == student.pk)
    assert mine["status"] == "partial"
    assert mine["amount_paid"] == "20000.00"
    assert mine["balance"] == "25000.00"


def test_full_payment_marks_the_fee_paid(parent_client, student, fee):
    row = student_fee(student, fee)
    row.amount_paid = Decimal("45000.00")
    row.save()

    body = parent_client.get("/api/parent/fees/").json()

    mine = next(entry for entry in body["fees"] if entry["student"] == student.pk)
    assert mine["status"] == "paid"
    assert mine["balance"] == "0.00"


def test_payment_history_is_scoped_to_the_parent(parent_client, parent, other_parent, student, outsider, fee):
    other_row = StudentFee.objects.create(student=outsider, fee=fee)
    Payment.objects.create(
        parent=parent,
        student_fee=student_fee(student, fee),
        amount=Decimal("10000.00"),
        reference="FEE-MINE",
    )
    Payment.objects.create(
        parent=other_parent,
        student_fee=other_row,
        amount=Decimal("5000.00"),
        reference="FEE-THEIRS",
    )

    response = parent_client.get("/api/parent/payments/")

    assert response.status_code == 200
    references = [row["reference"] for row in response.json()["payments"]]
    assert references == ["FEE-MINE"]


# ---------------------------------------------------------------------------
# Report cards
# ---------------------------------------------------------------------------
def test_parent_can_open_a_wards_report_card(parent_client, student, subject, session, term):
    make_result(student, subject, session, term, exam=40)

    response = parent_client.get(
        f"/api/students/{student.pk}/report-card/?session={session.pk}&term={term.pk}"
    )

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/html")


def test_parent_cannot_open_another_familys_report_card(other_parent_client, student, subject, session, term):
    make_result(student, subject, session, term, exam=40)

    response = other_parent_client.get(
        f"/api/students/{student.pk}/report-card/?session={session.pk}&term={term.pk}"
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Initialising a payment
# ---------------------------------------------------------------------------
def initialize_url():
    return "/api/payments/initialize/"


def test_initialize_returns_a_checkout_url(monkeypatch, parent_client, parent, student, fee):
    row = student_fee(student, fee)
    calls = {}

    def fake_initialize(**kwargs):
        calls.update(kwargs)
        return {"authorization_url": "https://checkout.paystack.com/abc123", "access_code": "abc123"}

    monkeypatch.setattr("core.parents.initialize_transaction", fake_initialize)

    response = parent_client.post(initialize_url(), {"student_fee_id": row.pk}, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["authorization_url"] == "https://checkout.paystack.com/abc123"
    assert calls["amount_kobo"] == 4500000
    assert calls["email"] == "chioma@example.com"
    assert calls["reference"] == body["reference"]

    payment = Payment.objects.get(reference=body["reference"])
    assert payment.parent_id == parent.pk
    assert payment.status == Payment.PENDING
    assert payment.amount == Decimal("45000.00")


def test_initialize_accepts_a_part_payment(monkeypatch, parent_client, student, fee):
    row = student_fee(student, fee)
    monkeypatch.setattr(
        "core.parents.initialize_transaction",
        lambda **kwargs: {"authorization_url": "https://checkout.paystack.com/part"},
    )

    response = parent_client.post(
        initialize_url(), {"student_fee_id": row.pk, "amount": "15000.00"}, format="json"
    )

    assert response.status_code == 201
    assert Payment.objects.get().amount == Decimal("15000.00")


def test_initialize_rejects_more_than_the_balance(parent_client, student, fee):
    row = student_fee(student, fee)

    response = parent_client.post(
        initialize_url(), {"student_fee_id": row.pk, "amount": "99999.00"}, format="json"
    )

    assert response.status_code == 400
    assert not Payment.objects.exists()


def test_initialize_rejects_a_paid_fee(parent_client, student, fee):
    row = student_fee(student, fee)
    row.amount_paid = Decimal("45000.00")
    row.save()

    response = parent_client.post(initialize_url(), {"student_fee_id": row.pk}, format="json")

    assert response.status_code == 400


def test_initialize_rejects_another_familys_fee(parent_client, outsider, fee):
    row = StudentFee.objects.create(student=outsider, fee=fee)

    response = parent_client.post(initialize_url(), {"student_fee_id": row.pk}, format="json")

    assert response.status_code == 403
    assert not Payment.objects.exists()


def test_initialize_requires_a_fee_id(parent_client):
    assert parent_client.post(initialize_url(), {}, format="json").status_code == 400


def test_initialize_without_paystack_key_fails_readably(settings, parent_client, student, fee):
    settings.PAYSTACK_SECRET_KEY = ""
    row = student_fee(student, fee)

    response = parent_client.post(initialize_url(), {"student_fee_id": row.pk}, format="json")

    assert response.status_code == 503
    assert "not set up" in response.json()["detail"]
    assert Payment.objects.get().status == Payment.FAILED


def test_student_cannot_initialize_a_payment(student_client, student, fee, monkeypatch):
    row = student_fee(student, fee)
    monkeypatch.setattr("core.parents.initialize_transaction", lambda **kwargs: {"authorization_url": "x"})

    assert student_client.post(initialize_url(), {"student_fee_id": row.pk}, format="json").status_code == 403
