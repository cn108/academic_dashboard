"""Teacher/staff temporary-password reset permissions."""

import re

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient


def reset_url(student):
    return f"/api/students/{student.pk}/reset-password/"


def ward_reset_url(student):
    return f"/api/parent/wards/{student.pk}/reset-password/"


@pytest.fixture
def staff_client(db):
    admin = User.objects.create_user("principal-reset", password="Principal!2026", is_staff=True)
    client = APIClient()
    client.force_authenticate(admin)
    return client


def test_class_teacher_can_reset_students_password(teacher_client, student):
    response = teacher_client.post(reset_url(student))

    assert response.status_code == 200
    temporary_password = response.json()["temporary_password"]
    assert re.fullmatch(r"[A-Za-z0-9]{16}", temporary_password)
    student.refresh_from_db()
    assert student.check_password(temporary_password)
    assert student.profile.must_change_password is True


def test_reset_password_is_generated_and_only_returned_in_reset_response(teacher_client, student):
    first = teacher_client.post(reset_url(student)).json()["temporary_password"]
    second = teacher_client.post(reset_url(student)).json()["temporary_password"]

    assert first != second
    assert teacher_client.get("/api/me/").status_code == 200
    # The next login requires this to be changed; the API does not persist or
    # return the temporary password again after the reset response.
    student.refresh_from_db()
    assert student.profile.must_change_password is True


def test_another_class_teacher_cannot_reset_student(other_teacher_client, student):
    response = other_teacher_client.post(reset_url(student))

    assert response.status_code == 403


def test_student_cannot_reset_self(student_client, student):
    assert student_client.post(reset_url(student)).status_code == 403


def test_parent_cannot_reset_ward(parent_client, student):
    assert parent_client.post(ward_reset_url(student)).status_code == 403


def test_only_staff_can_use_parent_ward_reset_endpoint(teacher_client, student, parent, staff_client):
    assert teacher_client.post(ward_reset_url(student)).status_code == 403

    response = staff_client.post(ward_reset_url(student))

    assert response.status_code == 200
    temporary_password = response.json()["temporary_password"]
    student.refresh_from_db()
    assert student.check_password(temporary_password)
    assert student.profile.must_change_password is True


def test_staff_can_reset_any_students_password(staff_client, outsider):
    response = staff_client.post(reset_url(outsider))

    assert response.status_code == 200
    assert response.json()["student_id"] == outsider.pk


def test_parent_ward_reset_returns_not_found_for_nonexistent_student(parent_client):
    assert parent_client.post("/api/parent/wards/987654/reset-password/").status_code == 403
