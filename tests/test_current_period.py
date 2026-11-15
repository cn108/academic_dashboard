"""The school profile is the only authority for the app-wide current period."""

import pytest

from core.models import AcademicSession, School, Term

pytestmark = pytest.mark.django_db


def test_school_save_keeps_exactly_one_current_term(session, term):
    second = Term.objects.get_or_create(session=session, name=Term.SECOND)[0]
    school = School.load()

    school.current_term = second
    school.save()

    assert list(Term.objects.filter(is_current=True)) == [second]
    assert Term.current() == second
    assert school.current_session_id == session.pk
    assert AcademicSession.current() == session

    school.current_term = term
    school.save()

    assert list(Term.objects.filter(is_current=True)) == [term]
    assert Term.current() == term


def test_term_current_ignores_stale_is_current_flags(session, term):
    """A legacy flag left on another term must not override the school profile."""
    second = Term.objects.get_or_create(session=session, name=Term.SECOND)[0]
    Term.objects.update(is_current=False)
    Term.objects.filter(pk=second.pk).update(is_current=True)

    assert term.pk != second.pk
    assert Term.current() == term
    assert Term.objects.get(is_current=True) == second


def test_clearing_the_school_term_clears_the_term_flag(session, term):
    school = School.load()

    school.current_term = None
    school.save()

    assert Term.current() is None
    assert not Term.objects.filter(is_current=True).exists()
    assert AcademicSession.current() == session


def test_academic_session_current_follows_the_school(session, term):
    other_session = AcademicSession.objects.create(name="2026/2027")
    other_term = Term.objects.create(session=other_session, name=Term.FIRST)

    school = School.load()
    school.current_term = other_term
    school.save()

    assert AcademicSession.current() == other_session
    assert Term.current() == other_term
    assert AcademicSession.objects.get(is_current=True) == other_session
    assert Term.objects.get(is_current=True) == other_term
