from django.db import migrations


def backfill_current_period(apps, schema_editor):
    """Adopt the legacy ``is_current`` flags into the school profile.

    The school row is the source of truth after this migration, but existing
    databases may only have the flags set. Copy them across once, preferring a
    term that belongs to the chosen session, then rewrite the flags from the
    resulting school row so exactly one session and one term stay marked.
    """

    School = apps.get_model("core", "School")
    AcademicSession = apps.get_model("core", "AcademicSession")
    Term = apps.get_model("core", "Term")

    school = School.objects.order_by("pk").first()
    if school is None:
        return

    term = Term.objects.filter(pk=school.current_term_id).first() if school.current_term_id else None
    session = (
        AcademicSession.objects.filter(pk=school.current_session_id).first()
        if school.current_session_id
        else None
    )

    if term is None:
        flagged = Term.objects.filter(is_current=True)
        if session is not None:
            term = flagged.filter(session_id=session.pk).order_by("name").first()
        if term is None:
            term = flagged.order_by("session__name", "name").first()

    if term is not None:
        session = AcademicSession.objects.filter(pk=term.session_id).first()
    elif session is None:
        session = AcademicSession.objects.filter(is_current=True).order_by("-name").first()
        if session is None:
            session = AcademicSession.objects.order_by("-name").first()

    School.objects.filter(pk=school.pk).update(current_session=session, current_term=term)

    AcademicSession.objects.update(is_current=False)
    if session is not None:
        AcademicSession.objects.filter(pk=session.pk).update(is_current=True)

    Term.objects.update(is_current=False)
    if term is not None:
        Term.objects.filter(pk=term.pk).update(is_current=True)


class Migration(migrations.Migration):
    dependencies = [("core", "0023_lessonresource_quiz_question_quizattempt_and_more")]

    operations = [migrations.RunPython(backfill_current_period, migrations.RunPython.noop)]
