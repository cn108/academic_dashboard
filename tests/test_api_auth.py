import pytest
from django.urls import reverse

from core.models import Profile

PASSWORD = "Sup3rSecret!42"


@pytest.mark.django_db
def test_student_logs_in_with_admission_number(client, student, settings):
    settings.AXES_ENABLED = False

    response = client.post(
        reverse("token_obtain_pair"),
        {"username": "JSS2A-001", "password": PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert "access" in response.json()


@pytest.mark.django_db
def test_me_reports_class_and_admission_number(student_client, student, school_class):
    payload = student_client.get(reverse("api-me")).json()

    assert payload["role"] == Profile.STUDENT
    assert payload["admission_number"] == "JSS2A-001"
    assert payload["school_class"] == school_class.pk
    assert payload["class_name"] == "JSS 2A"
    assert payload["must_change_password"] is False


@pytest.mark.django_db
def test_me_reports_teacher_role(teacher_client):
    payload = teacher_client.get(reverse("api-me")).json()

    assert payload["role"] == Profile.TEACHER
    assert payload["class_name"] is None


@pytest.mark.django_db
def test_public_registration_endpoints_are_gone(client):
    assert client.post("/api/register/", {}, content_type="application/json").status_code == 404
    assert client.get("/register/").status_code == 404
    assert client.get("/login/").status_code == 404


@pytest.mark.django_db
def test_teacher_accounts_cannot_be_self_created(client, settings):
    """Only a superuser can create teachers — via the admin, not the API."""
    settings.AXES_ENABLED = False

    response = client.post(
        reverse("token_obtain_pair"),
        {"username": "brand-new-teacher", "password": PASSWORD},
        content_type="application/json",
    )

    assert response.status_code == 401


@pytest.mark.django_db
def test_password_change_requires_the_current_password(student_client, student):
    response = student_client.post(
        reverse("api-password-change"),
        {"current_password": "wrong-password", "new_password": "An0therSecret!7"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "current_password" in response.json()


@pytest.mark.django_db
def test_password_change_weak_password_is_rejected(student_client):
    response = student_client.post(
        reverse("api-password-change"),
        {"current_password": PASSWORD, "new_password": "123"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "new_password" in response.json()


@pytest.mark.django_db
def test_password_change_clears_the_must_change_flag(student_client, student):
    profile = student.profile
    profile.must_change_password = True
    profile.save()

    response = student_client.post(
        reverse("api-password-change"),
        {"current_password": PASSWORD, "new_password": "An0therSecret!7"},
        content_type="application/json",
    )

    assert response.status_code == 200, response.content
    assert "access" in response.json()

    profile.refresh_from_db()
    student.refresh_from_db()
    assert profile.must_change_password is False
    assert student.check_password("An0therSecret!7") is True


@pytest.mark.django_db
def test_anonymous_users_cannot_read_the_api(client):
    # SessionAuthentication is the first backend, so DRF answers 403 not 401.
    assert client.get(reverse("api-me")).status_code in (401, 403)


@pytest.mark.django_db
def test_health_endpoint_is_open(client):
    response = client.get(reverse("api-health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
