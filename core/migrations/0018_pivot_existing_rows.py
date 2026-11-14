"""Carry legacy rows into the new school structure.

Old assignments were personal tasks with a progress status; they become published
class work. Legacy subjects belonged to a user rather than a class, so they are
removed. A first academic session and its three terms are created so the API has
a current term out of the box.
"""

from django.db import migrations

SESSION_NAME = "2025/2026"
TERM_NAMES = ("First Term", "Second Term", "Third Term")


def forwards(apps, schema_editor):
    Assignment = apps.get_model("core", "Assignment")
    for assignment in Assignment.objects.all():
        assignment.status = "published"
        if assignment.published_at is None:
            assignment.published_at = assignment.created_at
        assignment.save(update_fields=["status", "published_at"])

    Subject = apps.get_model("core", "Subject")
    Subject.objects.filter(school_class__isnull=True).delete()

    AcademicSession = apps.get_model("core", "AcademicSession")
    Term = apps.get_model("core", "Term")

    session, _created = AcademicSession.objects.get_or_create(name=SESSION_NAME)
    if not session.is_current:
        AcademicSession.objects.exclude(pk=session.pk).update(is_current=False)
        session.is_current = True
        session.save(update_fields=["is_current"])

    for name in TERM_NAMES:
        Term.objects.get_or_create(session=session, name=name)

    if not Term.objects.filter(is_current=True).exists():
        first = Term.objects.filter(session=session, name=TERM_NAMES[0]).first()
        if first is not None:
            first.is_current = True
            first.save(update_fields=["is_current"])


def backwards(apps, schema_editor):
    """No-op: the legacy rows cannot be reconstructed."""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0017_academicsession_announcement_lessonnote_result_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
