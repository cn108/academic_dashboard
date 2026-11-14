import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import AcademicSession, Profile, SchoolClass, Subject, Term

PASSWORD = "Sup3rSecret!42"
DEFAULT_STUDENT_PASSWORD = "Student@1234"


def make_user(username, role, **extra):
    user = User.objects.create_user(username=username, password=PASSWORD, **extra)
    Profile.objects.update_or_create(user=user, defaults={"role": role})
    return user


@pytest.fixture
def session(db):
    # Migration 0018 already creates the current session; reuse it.
    session, _created = AcademicSession.objects.get_or_create(name="2025/2026")
    session.is_current = True
    session.save()
    return session


@pytest.fixture
def term(session):
    term, _created = Term.objects.get_or_create(session=session, name=Term.FIRST)
    term.is_current = True
    term.save()
    return term


@pytest.fixture
def teacher(db):
    return make_user("ada", Profile.TEACHER, first_name="Ada", last_name="Obi")


@pytest.fixture
def other_teacher(db):
    return make_user("bello", Profile.TEACHER, first_name="Bello", last_name="Sani")


@pytest.fixture
def school_class(db, teacher):
    return SchoolClass.objects.create(name="JSS 2A", level="JSS 2", class_teacher=teacher)


@pytest.fixture
def other_class(db, other_teacher):
    return SchoolClass.objects.create(name="JSS 2B", level="JSS 2", class_teacher=other_teacher)


@pytest.fixture
def subject(school_class, teacher):
    return Subject.objects.create(name="Mathematics", school_class=school_class, teacher=teacher)


@pytest.fixture
def student(db, school_class):
    user = make_user("JSS2A-001", Profile.STUDENT, first_name="Chidera", last_name="Okafor")
    profile = user.profile
    profile.admission_number = "JSS2A-001"
    profile.gender = Profile.FEMALE
    profile.school_class = school_class
    profile.save()
    return user


@pytest.fixture
def classmate(db, school_class):
    user = make_user("JSS2A-002", Profile.STUDENT, first_name="Emeka", last_name="Nwosu")
    profile = user.profile
    profile.admission_number = "JSS2A-002"
    profile.school_class = school_class
    profile.save()
    return user


@pytest.fixture
def outsider(db, other_class):
    user = make_user("JSS2B-001", Profile.STUDENT, first_name="Fatima", last_name="Bello")
    profile = user.profile
    profile.admission_number = "JSS2B-001"
    profile.school_class = other_class
    profile.save()
    return user


@pytest.fixture
def teacher_client(teacher):
    client = APIClient()
    client.force_authenticate(teacher)
    return client


@pytest.fixture
def student_client(student):
    client = APIClient()
    client.force_authenticate(student)
    return client


@pytest.fixture
def other_teacher_client(other_teacher):
    client = APIClient()
    client.force_authenticate(other_teacher)
    return client


@pytest.fixture
def media_root(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path
