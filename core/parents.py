"""Parent portal API and Paystack fee payments.

A parent account is linked to one or more students by :class:`ParentStudentLink`.
Everything here is scoped to those links: a parent only ever sees their own wards'
results, fees and payments, and can only start a payment for a ward's fee.
"""

import json
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Attendance,
    Fee,
    ParentStudentLink,
    Payment,
    Profile,
    PublishStatus,
    Result,
    StudentFee,
    Term,
    role_of,
)
from .paystack import PaystackError, initialize_transaction, verify_signature
from .views import resolve_period

# "Attendance rate" needs a window because Attendance is not tied to a term.
ATTENDANCE_WINDOW_DAYS = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def require_parent(request) -> None:
    """Staff may look in; students and teachers cannot use the parent portal."""
    if role_of(request.user) == Profile.PARENT or request.user.is_staff:
        return
    raise PermissionDenied("Only parent accounts can open the parent portal.")


def parent_links(user):
    return ParentStudentLink.objects.filter(parent=user).select_related("student__profile__school_class")


def ensure_student_fees(student, session, term) -> list[StudentFee]:
    """Create the student's rows for every fee that applies to their class level."""
    profile = getattr(student, "profile", None)
    school_class = profile.school_class if profile else None
    if school_class is None:
        return []

    rows = []
    fees = Fee.objects.filter(session=session, term=term, class_level=school_class.level)
    for fee in fees:
        row, _created = StudentFee.objects.get_or_create(student=student, fee=fee)
        rows.append(row)
    return rows


def term_payload(term: Term | None) -> dict | None:
    if term is None:
        return None
    return {
        "id": term.pk,
        "name": term.name,
        "session": term.session_id,
        "session_name": term.session.name,
    }


def ward_row(link: ParentStudentLink, term: Term | None) -> dict:
    student = link.student
    profile = getattr(student, "profile", None)
    school_class = profile.school_class if profile else None

    averages: list[int] = []
    if term is not None:
        averages = list(
            Result.objects.filter(student=student, term=term, status=PublishStatus.PUBLISHED).values_list(
                "total", flat=True
            )
        )

    since = timezone.localdate() - timedelta(days=ATTENDANCE_WINDOW_DAYS)
    records = Attendance.objects.filter(student=student, date__gte=since)
    days_recorded = records.count()
    days_present = records.exclude(status=Attendance.ABSENT).count()

    return {
        "id": student.pk,
        "full_name": student.get_full_name() or student.username,
        "admission_number": profile.admission_number if profile else None,
        "class_name": school_class.name if school_class else None,
        "relationship": link.relationship,
        "subjects_count": len(averages),
        "average": round(sum(averages) / len(averages), 1) if averages else None,
        "attendance_days": days_recorded,
        "attendance_rate": round(days_present / days_recorded * 100) if days_recorded else None,
    }


def own_student_fee(request, student_fee_id) -> StudentFee:
    """Fetch a fee row only if it belongs to one of the caller's wards."""
    student_fee = get_object_or_404(StudentFee.objects.select_related("fee", "student"), pk=student_fee_id)
    if not ParentStudentLink.objects.filter(parent=request.user, student=student_fee.student).exists():
        raise PermissionDenied("That fee does not belong to one of your wards.")
    return student_fee


# ---------------------------------------------------------------------------
# Parent portal
# ---------------------------------------------------------------------------
class ParentWardsView(APIView):
    """Every linked child with their current-term average and attendance."""

    def get(self, request):
        require_parent(request)
        term = Term.current()
        links = parent_links(request.user)
        return Response(
            {
                "term": term_payload(term),
                "wards": [ward_row(link, term) for link in links],
            }
        )


class ParentFeesView(APIView):
    """Fees for the caller's wards in one term, with paid and outstanding totals."""

    def get(self, request):
        require_parent(request)
        session, term = resolve_period(request)

        rows = []
        for link in parent_links(request.user):
            student = link.student
            profile = getattr(student, "profile", None)
            for student_fee in ensure_student_fees(student, session, term):
                rows.append(
                    {
                        "id": student_fee.pk,
                        "student": student.pk,
                        "student_name": student.get_full_name() or student.username,
                        "class_name": (
                            profile.school_class.name if profile and profile.school_class else None
                        ),
                        "description": student_fee.fee.description,
                        "amount": str(student_fee.fee.amount),
                        "amount_paid": str(student_fee.amount_paid),
                        "balance": str(student_fee.balance),
                        "status": student_fee.status,
                        "session_id": session.pk,
                        "term_id": term.pk,
                        "term_name": term.name,
                    }
                )

        def total(field: str) -> str:
            return str(sum((Decimal(row[field]) for row in rows), Decimal("0.00")))

        return Response(
            {
                "session": {"id": session.pk, "name": session.name},
                "term": {"id": term.pk, "name": term.name},
                "fees": rows,
                "totals": {
                    "amount": total("amount"),
                    "amount_paid": total("amount_paid"),
                    "balance": total("balance"),
                },
            }
        )


class ParentPaymentsView(APIView):
    """The parent's payment history (successful and pending attempts)."""

    def get(self, request):
        require_parent(request)
        payments = (
            Payment.objects.filter(parent=request.user)
            .select_related("student_fee__fee__term", "student_fee__student")
            .order_by("-created_at")
        )
        rows = []
        for payment in payments:
            student = payment.student_fee.student
            rows.append(
                {
                    "id": payment.pk,
                    "student": student.pk,
                    "student_name": student.get_full_name() or student.username,
                    "description": payment.student_fee.fee.description,
                    "term_name": payment.student_fee.fee.term.name,
                    "amount": str(payment.amount),
                    "reference": payment.reference,
                    "gateway": payment.gateway,
                    "status": payment.status,
                    "paid_at": payment.paid_at,
                    "created_at": payment.created_at,
                }
            )
        return Response({"payments": rows})


# ---------------------------------------------------------------------------
# Paystack
# ---------------------------------------------------------------------------
class InitializePaymentView(APIView):
    """Start a Paystack transaction for one outstanding student fee."""

    def post(self, request):
        require_parent(request)
        student_fee_id = request.data.get("student_fee_id")
        if not student_fee_id:
            raise ValidationError({"student_fee_id": "Choose a fee to pay."})

        student_fee = own_student_fee(request, student_fee_id)
        balance = student_fee.balance
        if balance <= 0:
            raise ValidationError({"amount": "This fee is already fully paid."})

        amount = balance
        raw_amount = request.data.get("amount")
        if raw_amount not in (None, ""):
            try:
                amount = Decimal(str(raw_amount)).quantize(Decimal("0.01"))
            except (InvalidOperation, ValueError) as error:
                raise ValidationError({"amount": "Enter a valid amount."}) from error
            if amount <= 0:
                raise ValidationError({"amount": "The amount must be greater than zero."})
            if amount > balance:
                raise ValidationError({"amount": f"The outstanding balance is {balance}."})

        reference = f"FEE-{uuid.uuid4().hex[:16].upper()}"
        payment = Payment.objects.create(
            parent=request.user,
            student_fee=student_fee,
            amount=amount,
            reference=reference,
        )

        callback_url = f"{settings.FRONTEND_URL.rstrip('/')}/parent/fees" if settings.FRONTEND_URL else None
        try:
            data = initialize_transaction(
                email=request.user.email or settings.DEFAULT_FROM_EMAIL,
                amount_kobo=int(amount * 100),
                reference=reference,
                callback_url=callback_url,
                metadata={
                    "student_fee_id": student_fee.pk,
                    "student": student_fee.student_id,
                    "parent": request.user.pk,
                },
            )
        except PaystackError as error:
            payment.status = Payment.FAILED
            payment.save(update_fields=["status"])
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(
            {
                "authorization_url": data.get("authorization_url"),
                "access_code": data.get("access_code"),
                "reference": reference,
                "amount": str(amount),
            },
            status=status.HTTP_201_CREATED,
        )


@method_decorator(csrf_exempt, name="dispatch")
class PaystackWebhookView(APIView):
    """Paystack's server-to-server notification.

    CSRF does not apply (there is no browser session), so the HMAC SHA512
    signature over the raw body is the only authentication that matters.
    """

    authentication_classes = ()
    permission_classes = [AllowAny]

    def post(self, request):
        provided = request.headers.get("X-Paystack-Signature", "")
        if not verify_signature(request.body, provided):
            return Response({"detail": "Invalid signature."}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            event = json.loads(request.body or b"{}")
        except ValueError:
            return Response({"detail": "Malformed payload."}, status=status.HTTP_400_BAD_REQUEST)

        if event.get("event") != "charge.success":
            return Response({"status": "ignored"})

        payload = event.get("data") or {}
        reference = payload.get("reference") or ""
        with transaction.atomic():
            payment = Payment.objects.select_for_update().filter(reference=reference).first()
            if payment is None:
                # Nothing we started; acknowledge so Paystack stops retrying.
                return Response({"status": "unknown-reference"})
            if payment.status == Payment.SUCCESS:
                return Response({"status": "already-processed"})

            paid = payload.get("status") == "success"
            amount_kobo = int(payload.get("amount") or 0)
            if not paid or amount_kobo < int(payment.amount * 100):
                payment.status = Payment.FAILED
                payment.save(update_fields=["status"])
                return Response({"status": "rejected"})

            # Credit the fee first: the payment's post_save signal builds the
            # receipt from the fee's new balance.
            student_fee = payment.student_fee
            student_fee.amount_paid = student_fee.amount_paid + payment.amount
            student_fee.save()

            payment.status = Payment.SUCCESS
            payment.paid_at = timezone.now()
            payment.save(update_fields=["status", "paid_at"])

        return Response({"status": "ok"})
