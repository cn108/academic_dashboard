"""School branding: the public profile, the report-card masthead and the period sync."""

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from core.models import PublishStatus, Result, School, Term

SCHOOL_URL = "/api/school/"


def png_upload(name="crest.png"):
    buffer = BytesIO()
    Image.new("RGB", (12, 12), "green").save(buffer, "PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@pytest.fixture
def school(db):
    row = School.load()
    row.name = "Greenfield College"
    row.motto = "Knowledge and Integrity"
    row.address = "12 Awolowo Road, Ikoyi, Lagos"
    row.phone = "08031234567"
    row.email = "office@greenfield.example"
    row.save()
    return row


def test_school_profile_is_public_and_uses_defaults(db, settings):
    settings.SCHOOL_NAME = "Model Secondary School"

    response = APIClient().get(SCHOOL_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Model Secondary School"
    assert body["initials"] == "MSS"
    assert body["logo_url"] is None
    assert body["motto"] == ""


def test_school_profile_is_a_single_row(school, db):
    APIClient().get(SCHOOL_URL)
    APIClient().get(SCHOOL_URL)

    assert School.objects.count() == 1


def test_school_profile_returns_the_configured_branding(school):
    body = APIClient().get(SCHOOL_URL).json()

    assert body["name"] == "Greenfield College"
    assert body["motto"] == "Knowledge and Integrity"
    assert body["address"] == "12 Awolowo Road, Ikoyi, Lagos"
    assert body["phone"] == "08031234567"
    assert body["email"] == "office@greenfield.example"
    assert body["initials"] == "GC"


def test_logo_is_served_as_an_absolute_url(school, media_root):
    school.logo = png_upload()
    school.save()

    body = APIClient().get(SCHOOL_URL).json()

    assert body["logo_url"].startswith("http://testserver/media/school/")
    assert body["logo_url"].endswith("crest.png")


def test_school_period_syncs_the_app_wide_current_term(school, session, term):
    second, _created = Term.objects.get_or_create(session=session, name=Term.SECOND)

    school.current_term = second
    school.save()

    second.refresh_from_db()
    assert second.is_current is True
    assert Term.current() == second
    assert school.current_term_id == second.pk
    assert school.current_session_id == session.pk

    body = APIClient().get(SCHOOL_URL).json()
    assert body["current_term"]["name"] == Term.SECOND
    assert body["current_session"]["name"] == session.name


# ---------------------------------------------------------------------------
# Report card masthead
# ---------------------------------------------------------------------------
def make_result(student, subject, session, term):
    return Result.objects.create(
        student=student,
        subject=subject,
        session=session,
        term=term,
        ca1=8,
        ca2=9,
        ca3=11,
        exam=30,
        status=PublishStatus.PUBLISHED,
    )


def card_url(student, session, term):
    return f"/api/students/{student.pk}/report-card/?session={session.pk}&term={term.pk}"


def test_report_card_masthead_uses_school_branding(school, student_client, student, subject, session, term):
    make_result(student, subject, session, term)

    html = student_client.get(card_url(student, session, term)).content.decode()

    assert "Greenfield College" in html
    assert "Knowledge and Integrity" in html
    assert "12 Awolowo Road, Ikoyi, Lagos" in html
    assert "office@greenfield.example" in html
    assert '<div class="crest">GC</div>' in html
    assert "SMS" not in html


def test_report_card_shows_the_uploaded_logo(
    school, media_root, student_client, student, subject, session, term
):
    school.logo = png_upload()
    school.save()
    make_result(student, subject, session, term)

    html = student_client.get(card_url(student, session, term)).content.decode()

    assert 'class="crest" src="' in html
    assert "/media/school/" in html
    assert "Greenfield College logo" in html
    assert '<div class="crest">GC</div>' not in html


def test_report_card_falls_back_to_settings_without_a_school_row(
    student_client, student, subject, session, term, settings
):
    settings.SCHOOL_NAME = "Model Secondary School"
    make_result(student, subject, session, term)

    html = student_client.get(card_url(student, session, term)).content.decode()

    assert "Model Secondary School" in html
    assert '<div class="crest">MSS</div>' in html
