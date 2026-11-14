"""Bursar dashboard: summary maths, debtors ordering/search and the ledger export."""

from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from django.contrib.auth.models import User
from openpyxl import load_workbook
from rest_framework.test import APIClient

from core.models import AcademicSession, Fee, Profile, SchoolClass, StudentFee, Term
from tests.conftest import make_user

SUMMARY_URL = "/api/finance/summary/"
DEBTORS_URL = "/api/finance/debtors/"
LEDGER_URL = "/api/finance/ledger/"


@pytest.fixture
def staff_client(db):
    staff = User.objects.create_user("bursar", password="Bursar@2026", is_staff=True)
    client = APIClient()
    client.force_authenticate(staff)
    return client


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


def add_student(school_class, admission_number, first_name, last_name="Test"):
    user = make_user(admission_number, Profile.STUDENT, first_name=first_name, last_name=last_name)
    profile = user.profile
    profile.admission_number = admission_number
    profile.school_class = school_class
    profile.save()
    return user


def pay(student, fee, amount):
    row, _created = StudentFee.objects.get_or_create(student=student, fee=fee)
    row.amount_paid = Decimal(amount)
    row.save()
    return row


def url(base, session, term, **extra):
    params = f"?session={session.pk}&term={term.pk}"
    for key, value in extra.items():
        params += f"&{key}={value}"
    return base + params


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
def test_summary_totals_paid_and_debtors(staff_client, student, classmate, fee, session, term):
    pay(student, fee, "45000.00")
    pay(classmate, fee, "20000.00")

    response = staff_client.get(url(SUMMARY_URL, session, term))

    assert response.status_code == 200
    body = response.json()
    assert body["session"]["id"] == session.pk
    assert body["term"]["name"] == term.name
    assert body["total_expected"] == "90000.00"
    assert body["total_collected"] == "65000.00"
    assert body["outstanding"] == "25000.00"
    assert body["fully_paid_count"] == 1
    assert body["debtor_count"] == 1
    assert body["partial_count"] == 1
    assert body["unpaid_count"] == 0
    assert body["student_count"] == 2


def test_summary_sums_every_fee_for_the_level(staff_client, student, classmate, fee, bus_fee, session, term):
    pay(student, fee, "45000.00")
    pay(student, bus_fee, "2000.00")

    body = staff_client.get(url(SUMMARY_URL, session, term)).json()

    # Two bills per student: 57,000 expected each, 114,000 for the class.
    assert body["total_expected"] == "114000.00"
    assert body["total_collected"] == "47000.00"
    assert body["outstanding"] == "67000.00"
    assert body["debtor_count"] == 2


def test_summary_is_scoped_to_the_requested_term(staff_client, student, fee, session, term):
    second, _created = Term.objects.get_or_create(session=session, name=Term.SECOND)

    body = staff_client.get(url(SUMMARY_URL, session, second)).json()

    assert body["term"]["name"] == Term.SECOND
    # The fee belongs to the first term, so the second term bills nothing.
    assert body["total_expected"] == "0.00"
    assert body["total_collected"] == "0.00"
    assert body["debtor_count"] == 0
    assert body["fully_paid_count"] == 0


def test_summary_requires_a_staff_account(teacher_client, student_client, parent_client):
    assert teacher_client.get(SUMMARY_URL).status_code == 403
    assert student_client.get(SUMMARY_URL).status_code == 403
    assert parent_client.get(SUMMARY_URL).status_code == 403
    assert APIClient().get(SUMMARY_URL).status_code == 401


# ---------------------------------------------------------------------------
# Debtors
# ---------------------------------------------------------------------------
def test_debtors_are_ordered_by_highest_debt(staff_client, student, classmate, fee, session, term, parent):
    third = add_student(student.profile.school_class, "JSS2A-003", "Ngozi", "Eze")
    pay(classmate, fee, "20000.00")
    pay(third, fee, "45000.00")

    # Give the first guardian a phone number a bursar can call.
    profile = parent.profile
    profile.phone_number = "08031234567"
    profile.save()

    response = staff_client.get(url(DEBTORS_URL, session, term))

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    names = [row["full_name"] for row in body["results"]]
    assert names == ["Chidera Okafor", "Emeka Nwosu"]
    assert body["results"][0]["balance"] == "45000.00"
    assert body["results"][1]["balance"] == "25000.00"

    guardian = body["results"][0]["guardians"][0]
    assert guardian["name"] == "Chioma Okafor"
    assert guardian["phone"] == "08031234567"
    assert guardian["relationship"] == "Mother"
    assert guardian["email"] == "chioma@example.com"


def test_debtors_search_and_pagination(staff_client, school_class, fee, session, term):
    for index in range(25):
        add_student(school_class, f"JSS2A-{index:03d}", f"Student{index}", "Debtor")

    first_page = staff_client.get(url(DEBTORS_URL, session, term)).json()
    assert first_page["count"] == 25
    assert len(first_page["results"]) == 20
    assert first_page["next"] is not None

    second_page = staff_client.get(url(DEBTORS_URL, session, term, page=2)).json()
    assert len(second_page["results"]) == 5

    found = staff_client.get(url(DEBTORS_URL, session, term, search="Student7")).json()
    assert found["count"] == 1
    assert found["results"][0]["admission_number"] == "JSS2A-007"

    by_admission = staff_client.get(url(DEBTORS_URL, session, term, search="JSS2A-013")).json()
    assert by_admission["count"] == 1

    missing = staff_client.get(url(DEBTORS_URL, session, term, search="Nobody")).json()
    assert missing["count"] == 0


def test_debtors_requires_staff(teacher_client, student_client):
    assert teacher_client.get(DEBTORS_URL).status_code == 403
    assert student_client.get(DEBTORS_URL).status_code == 403


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------
def test_ledger_json_lists_every_student(staff_client, student, classmate, parent, fee, session, term):
    pay(student, fee, "45000.00")

    # A class with no fees configured still appears in the ledger.
    other_level = SchoolClass.objects.create(name="JSS 1A", level="JSS 1")
    add_student(other_level, "JSS1A-001", "Halima", "Yusuf")

    body = staff_client.get(url(LEDGER_URL, session, term)).json()

    assert body["session"]["name"] == session.name
    assert body["summary"]["total_expected"] == "90000.00"
    rows = {row["admission_number"]: row for row in body["students"]}
    assert rows["JSS2A-001"]["status"] == "paid"
    assert rows["JSS2A-002"]["status"] == "unpaid"
    assert rows["JSS2A-002"]["balance"] == "45000.00"
    assert rows["JSS1A-001"]["status"] == "no_fees"
    assert rows["JSS1A-001"]["balance"] == "0.00"
    assert rows["JSS2A-001"]["guardians"][0]["phone"] is not None


def test_ledger_downloads_a_formatted_workbook(staff_client, student, classmate, fee, session, term):
    pay(student, fee, "45000.00")
    pay(classmate, fee, "20000.00")

    response = staff_client.get(url(LEDGER_URL, session, term, format="xlsx"))

    assert response.status_code == 200
    assert response["Content-Type"] == ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert 'filename="fee-ledger-' in response["Content-Disposition"]
    assert response["Content-Disposition"].endswith('.xlsx"')

    sheet = load_workbook(BytesIO(response.content)).active
    assert sheet.title == "Fee ledger"
    assert "Fee ledger" in sheet["A1"].value
    assert term.name in sheet["A1"].value

    headers = [sheet.cell(row=4, column=column).value for column in range(1, 8)]
    assert headers == [
        "Admission No",
        "Student",
        "Class",
        "Expected fees",
        "Amount paid",
        "Balance",
        "Status",
    ]

    rows = {}
    for row in range(5, 7):
        rows[sheet.cell(row=row, column=1).value] = [
            sheet.cell(row=row, column=column).value for column in range(2, 8)
        ]
    assert rows["JSS2A-001"] == [
        "Chidera Okafor",
        "JSS 2A",
        45000,
        45000,
        0,
        "Paid",
    ]
    assert rows["JSS2A-002"] == [
        "Emeka Nwosu",
        "JSS 2A",
        45000,
        20000,
        25000,
        "Part payment",
    ]

    totals = [sheet.cell(row=7, column=column).value for column in range(1, 8)]
    assert totals == [None, "TOTAL", None, 90000, 65000, 25000, None]


def test_ledger_requires_staff(teacher_client, parent_client):
    assert teacher_client.get(LEDGER_URL).status_code == 403
    assert parent_client.get(LEDGER_URL).status_code == 403


def test_summary_rejects_a_session_that_does_not_match_the_term(staff_client, session, term):
    other_session = AcademicSession.objects.create(name="2024/2025", start_date=date(2024, 9, 1))

    response = staff_client.get(f"{SUMMARY_URL}?session={other_session.pk}&term={term.pk}")

    assert response.status_code == 400
    assert "session" in response.json()
