"""Bursar reporting: one consistent fee position per student for a period.

The parent portal, the finance dashboard, the debtors list and the Excel ledger
all build their rows from :func:`student_fee_positions`, so the total a bursar
sees is the same total a parent sees on their own fee page.
"""

from __future__ import annotations

from decimal import Decimal

from .models import Fee, ParentStudentLink, Profile, StudentFee

ZERO = Decimal("0.00")
CENT = Decimal("0.01")

NO_FEES = "no_fees"


def money(value) -> Decimal:
    """Round a database amount to two decimal places."""
    return Decimal(value).quantize(CENT)


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


def sync_student_fees(session, term) -> None:
    """Give every enrolled student their rows, so a first visit shows real totals.

    Idempotent: existing payments are never touched, and a student without a
    class has no applicable fee rows.
    """
    profiles = Profile.objects.filter(role=Profile.STUDENT, school_class__isnull=False).select_related("user")
    for profile in profiles:
        ensure_student_fees(profile.user, session, term)


def _guardian_rows() -> dict[int, list[dict]]:
    guardians: dict[int, list[dict]] = {}
    links = ParentStudentLink.objects.select_related("parent__profile").order_by(
        "parent__first_name", "parent__last_name", "parent__username"
    )
    for link in links:
        parent = link.parent
        profile = getattr(parent, "profile", None)
        guardians.setdefault(link.student_id, []).append(
            {
                "parent": parent.pk,
                "name": parent.get_full_name() or parent.get_username(),
                "relationship": link.get_relationship_display(),
                "phone": profile.phone_number if profile else "",
                "email": parent.email,
            }
        )
    return guardians


def student_fee_positions(session, term) -> list[dict]:
    """Every student with their expected, paid and outstanding totals.

    A student whose class level has no fee for the period is included with
    ``status == "no_fees"`` so the ledger still lists the whole school, but they
    are left out of the summary and debtor counts.
    """
    sync_student_fees(session, term)

    profiles = (
        Profile.objects.filter(role=Profile.STUDENT)
        .select_related("user", "school_class")
        .order_by("user__first_name", "user__last_name", "user__username")
    )

    totals: dict[int, dict] = {}
    student_fees = StudentFee.objects.filter(fee__session=session, fee__term=term).select_related("fee")
    for student_fee in student_fees:
        bucket = totals.setdefault(student_fee.student_id, {"expected": ZERO, "paid": ZERO, "balance": ZERO})
        bucket["expected"] += money(student_fee.fee.amount)
        bucket["paid"] += money(student_fee.amount_paid)
        bucket["balance"] += money(student_fee.balance)

    guardians = _guardian_rows()

    positions = []
    for profile in profiles:
        student = profile.user
        bucket = totals.get(student.pk, {"expected": ZERO, "paid": ZERO, "balance": ZERO})
        expected = money(bucket["expected"])
        paid = money(bucket["paid"])
        balance = money(max(bucket["balance"], ZERO))
        if expected <= 0:
            status = NO_FEES
        elif balance <= 0:
            status = StudentFee.PAID
        elif paid > 0:
            status = StudentFee.PARTIAL
        else:
            status = StudentFee.UNPAID

        positions.append(
            {
                "student": student.pk,
                "full_name": student.get_full_name() or student.get_username(),
                "admission_number": profile.admission_number,
                "class_name": profile.school_class.name if profile.school_class else None,
                "expected": expected,
                "paid": paid,
                "balance": balance,
                "status": status,
                "guardians": guardians.get(student.pk, []),
            }
        )
    return positions


def billed_positions(positions: list[dict]) -> list[dict]:
    """Students who actually owe the school something this period."""
    return [row for row in positions if row["expected"] > 0]


def finance_summary(positions: list[dict]) -> dict:
    """Money and headcounts for the bursar's cards."""
    billed = billed_positions(positions)
    expected = sum((row["expected"] for row in billed), ZERO)
    collected = sum((row["paid"] for row in billed), ZERO)
    outstanding = sum((row["balance"] for row in billed), ZERO)

    return {
        "student_count": len(positions),
        "billed_student_count": len(billed),
        "total_expected": money(expected),
        "total_collected": money(collected),
        "outstanding": money(outstanding),
        "fully_paid_count": sum(1 for row in billed if row["balance"] <= 0),
        "partial_count": sum(1 for row in billed if row["status"] == StudentFee.PARTIAL),
        "unpaid_count": sum(1 for row in billed if row["status"] == StudentFee.UNPAID),
        "debtor_count": sum(1 for row in billed if row["balance"] > 0),
    }


def debtors(positions: list[dict], search: str = "") -> list[dict]:
    """Outstanding students, biggest debt first, optionally filtered by ``search``."""
    rows = [row for row in positions if row["balance"] > 0]
    needle = search.strip().casefold()
    if needle:
        rows = [row for row in rows if needle in _search_text(row)]
    return sorted(rows, key=lambda row: (-row["balance"], row["full_name"]))


def _search_text(row: dict) -> str:
    parts = [row["full_name"], row["admission_number"] or "", row["class_name"] or ""]
    for guardian in row["guardians"]:
        parts.extend([guardian["name"], guardian["phone"] or ""])
    return " ".join(parts).casefold()


def ledger_row(row: dict) -> dict:
    """JSON-safe form of one ledger line."""
    return {
        "student": row["student"],
        "full_name": row["full_name"],
        "admission_number": row["admission_number"],
        "class_name": row["class_name"],
        "expected": str(row["expected"]),
        "paid": str(row["paid"]),
        "balance": str(row["balance"]),
        "status": row["status"],
        "guardians": row["guardians"],
    }


def summary_payload(summary: dict) -> dict:
    """The summary with amounts serialised the way the rest of the API does it."""
    payload = dict(summary)
    for field in ("total_expected", "total_collected", "outstanding"):
        payload[field] = str(payload[field])
    return payload
