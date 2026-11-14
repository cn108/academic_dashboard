"""Paystack webhook: signature verification, idempotency and balance updates."""

import json
from decimal import Decimal

import pytest
from django.test import Client

from core.models import Fee, Payment, StudentFee
from core.paystack import signature_for

WEBHOOK_URL = "/api/webhooks/paystack/"


@pytest.fixture
def fee(session, term, school_class):
    return Fee.objects.create(
        session=session,
        term=term,
        class_level=school_class.level,
        amount=Decimal("50000.00"),
        description="Tuition and levies",
    )


@pytest.fixture
def student_fee(student, fee):
    return StudentFee.objects.create(student=student, fee=fee)


@pytest.fixture
def pending_payment(parent, student_fee):
    return Payment.objects.create(
        parent=parent,
        student_fee=student_fee,
        amount=Decimal("20000.00"),
        reference="FEE-WEBHOOK-0001",
    )


def charge_payload(reference, amount_kobo=2000000, status="success"):
    return json.dumps(
        {
            "event": "charge.success",
            "data": {
                "reference": reference,
                "amount": amount_kobo,
                "status": status,
                "currency": "NGN",
            },
        }
    )


def post_webhook(body, signature=None, client=None):
    client = client or Client()
    headers = {"HTTP_X_PAYSTACK_SIGNATURE": signature} if signature is not None else {}
    return client.post(WEBHOOK_URL, data=body, content_type="application/json", **headers)


def test_valid_signature_marks_the_payment_successful(pending_payment, student_fee):
    body = charge_payload(pending_payment.reference)

    response = post_webhook(body, signature_for(body.encode()))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    pending_payment.refresh_from_db()
    assert pending_payment.status == Payment.SUCCESS
    assert pending_payment.paid_at is not None

    student_fee.refresh_from_db()
    assert student_fee.amount_paid == Decimal("20000.00")
    assert student_fee.balance == Decimal("30000.00")
    assert student_fee.status == StudentFee.PARTIAL


def test_valid_signature_for_a_full_payment_marks_the_fee_paid(pending_payment, student_fee):
    pending_payment.amount = Decimal("50000.00")
    pending_payment.save(update_fields=["amount"])
    body = charge_payload(pending_payment.reference, amount_kobo=5000000)

    post_webhook(body, signature_for(body.encode()))

    student_fee.refresh_from_db()
    assert student_fee.status == StudentFee.PAID
    assert student_fee.balance == Decimal("0.00")


def test_missing_signature_is_rejected(pending_payment):
    response = post_webhook(charge_payload(pending_payment.reference))

    assert response.status_code == 401
    pending_payment.refresh_from_db()
    assert pending_payment.status == Payment.PENDING


def test_wrong_signature_is_rejected(pending_payment, student_fee):
    body = charge_payload(pending_payment.reference)

    response = post_webhook(body, signature="0" * 128)

    assert response.status_code == 401
    pending_payment.refresh_from_db()
    student_fee.refresh_from_db()
    assert pending_payment.status == Payment.PENDING
    assert student_fee.amount_paid == 0


def test_webhook_is_csrf_exempt(pending_payment):
    body = charge_payload(pending_payment.reference)

    response = post_webhook(body, signature_for(body.encode()), client=Client(enforce_csrf_checks=True))

    assert response.status_code == 200


def test_replayed_event_does_not_double_count(pending_payment, student_fee):
    body = charge_payload(pending_payment.reference)
    signature = signature_for(body.encode())

    post_webhook(body, signature)
    second = post_webhook(body, signature)

    assert second.status_code == 200
    assert second.json()["status"] == "already-processed"
    student_fee.refresh_from_db()
    assert student_fee.amount_paid == Decimal("20000.00")


def test_underpayment_does_not_credit_the_fee(pending_payment, student_fee):
    body = charge_payload(pending_payment.reference, amount_kobo=500000)

    post_webhook(body, signature_for(body.encode()))

    pending_payment.refresh_from_db()
    student_fee.refresh_from_db()
    assert pending_payment.status == Payment.FAILED
    assert student_fee.amount_paid == 0


def test_unknown_reference_is_acknowledged(pending_payment):
    body = charge_payload("FEE-NOT-OURS")

    response = post_webhook(body, signature_for(body.encode()))

    assert response.status_code == 200
    assert response.json()["status"] == "unknown-reference"


def test_other_events_are_ignored(pending_payment):
    body = json.dumps({"event": "transfer.success", "data": {"reference": pending_payment.reference}})

    response = post_webhook(body, signature_for(body.encode()))

    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    pending_payment.refresh_from_db()
    assert pending_payment.status == Payment.PENDING


def test_a_failed_charge_marks_the_payment_failed(pending_payment):
    body = charge_payload(pending_payment.reference, status="failed")

    post_webhook(body, signature_for(body.encode()))

    pending_payment.refresh_from_db()
    assert pending_payment.status == Payment.FAILED
