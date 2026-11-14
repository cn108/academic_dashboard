"""Seed a realistic Nigerian school for demos.

Idempotent: class sizes and scores are stable across repeated runs.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import (
    AcademicSession,
    Announcement,
    Assignment,
    Attendance,
    Fee,
    LessonNote,
    ParentStudentLink,
    Payment,
    Profile,
    PublishStatus,
    Result,
    Schedule,
    SchoolClass,
    StudentFee,
    Subject,
    Submission,
    Term,
)

TEACHER_USERNAME = "teacher"
TEACHER_PASSWORD = "teach-pass-1234"
PARENT_USERNAME = "parent"
PARENT_PASSWORD = "parent-pass-1234"
STUDENTS = [
    ("Chidera Okafor", "JSS2A-001", "F"),
    ("Emeka Nwosu", "JSS2A-002", "M"),
    ("Fatima Bello", "JSS2A-003", "F"),
    ("Ibrahim Musa", "JSS2A-004", "M"),
    ("Ngozi Eze", "JSS2A-005", "F"),
    ("Tunde Adeyemi", "JSS2A-006", "M"),
    ("Blessing Ojo", "JSS2A-007", "F"),
    ("Sani Abdullahi", "JSS2A-008", "M"),
    ("Amaka Obi", "JSS2A-009", "F"),
    ("Peter Danjuma", "JSS2A-010", "M"),
    ("Halima Yusuf", "JSS2A-011", "F"),
    ("Kelechi Umeh", "JSS2A-012", "M"),
]
SUBJECTS = ["Mathematics", "English Language", "Basic Science"]


class Command(BaseCommand):
    help = "Seed a demo school: class, teacher, students, results, notes and attendance."

    def handle(self, *args, **options):
        session, _ = AcademicSession.objects.get_or_create(name="2025/2026")
        session.is_current = True
        session.save()

        terms = {}
        for name in (Term.FIRST, Term.SECOND, Term.THIRD):
            term, _ = Term.objects.get_or_create(session=session, name=name)
            terms[name] = term
        terms[Term.FIRST].is_current = True
        terms[Term.FIRST].save()

        teacher, _ = User.objects.get_or_create(
            username=TEACHER_USERNAME,
            defaults={"first_name": "Ada", "last_name": "Obi", "email": "ada@school.example"},
        )
        teacher.set_password(TEACHER_PASSWORD)
        teacher.save()
        Profile.objects.update_or_create(user=teacher, defaults={"role": Profile.TEACHER})

        school_class, _ = SchoolClass.objects.get_or_create(
            name="JSS 2A",
            defaults={"level": "JSS 2", "class_teacher": teacher, "capacity": 50},
        )
        school_class.class_teacher = teacher
        school_class.save()

        subjects = {}
        for name in SUBJECTS:
            subject, _ = Subject.objects.update_or_create(
                school_class=school_class, name=name, defaults={"teacher": teacher}
            )
            subjects[name] = subject

        students = []
        for index, (full_name, admission_number, gender) in enumerate(STUDENTS):
            first_name, last_name = full_name.split(" ", 1)
            user, created = User.objects.get_or_create(
                username=admission_number,
                defaults={"first_name": first_name, "last_name": last_name},
            )
            if created:
                user.set_password(settings.DEFAULT_STUDENT_PASSWORD)
                user.save()
            Profile.objects.update_or_create(
                user=user,
                defaults={
                    "role": Profile.STUDENT,
                    "admission_number": admission_number,
                    "gender": gender,
                    "school_class": school_class,
                    "must_change_password": False,
                },
            )
            students.append(user)

            # Deterministic, believable scores.
            maths = 55 + (index * 3) % 40
            english = 60 + (index * 5) % 35
            science = 45 + (index * 7) % 45
            for subject_name, total_goal, status in (
                ("Mathematics", maths, PublishStatus.PUBLISHED),
                ("English Language", english, PublishStatus.PUBLISHED),
                ("Basic Science", science, PublishStatus.DRAFT),
            ):
                exam = min(60, max(0, total_goal - 28))
                result, _ = Result.objects.update_or_create(
                    student=user,
                    subject=subjects[subject_name],
                    session=session,
                    term=terms[Term.FIRST],
                    defaults={
                        "ca1": 8,
                        "ca2": 9,
                        "ca3": 11,
                        "exam": exam,
                        "created_by": teacher,
                        "status": status,
                    },
                )
                if status == PublishStatus.PUBLISHED:
                    result.publish()
                    result.save()

            # Previous term, so the student portal's term selector has history to show.
            for subject_name, total_goal in (
                ("Mathematics", 50 + (index * 5) % 45),
                ("English Language", 58 + (index * 3) % 38),
                ("Basic Science", 48 + (index * 6) % 42),
            ):
                exam = min(60, max(0, total_goal - 30))
                result, _ = Result.objects.update_or_create(
                    student=user,
                    subject=subjects[subject_name],
                    session=session,
                    term=terms[Term.SECOND],
                    defaults={
                        "ca1": 7,
                        "ca2": 8,
                        "ca3": 10,
                        "exam": exam,
                        "created_by": teacher,
                        "status": PublishStatus.PUBLISHED,
                    },
                )
                result.publish()
                result.save()

        # A parent account with two wards in the class, plus this term's fees.
        parent, _ = User.objects.get_or_create(
            username=PARENT_USERNAME,
            defaults={
                "first_name": "Chioma",
                "last_name": "Okafor",
                "email": "chioma.okafor@example.com",
            },
        )
        parent.set_password(PARENT_PASSWORD)
        parent.save()
        Profile.objects.update_or_create(
            user=parent,
            defaults={
                "role": Profile.PARENT,
                "phone_number": "08031234567",
                "phone_verified": True,
            },
        )
        for ward in (students[0], students[2]):
            ParentStudentLink.objects.update_or_create(
                parent=parent,
                student=ward,
                defaults={"relationship": ParentStudentLink.MOTHER},
            )

        fees = {}
        for description, amount in (
            ("Tuition and levies", Decimal("45000.00")),
            ("Bus service", Decimal("12000.00")),
        ):
            fee, _ = Fee.objects.update_or_create(
                session=session,
                term=terms[Term.FIRST],
                class_level=school_class.level,
                description=description,
                defaults={"amount": amount},
            )
            fees[description] = fee

        for ward in (students[0], students[2]):
            for fee in fees.values():
                StudentFee.objects.get_or_create(student=ward, fee=fee)

        tuition = StudentFee.objects.get(student=students[0], fee=fees["Tuition and levies"])
        tuition.amount_paid = Decimal("20000.00")
        tuition.save()
        Payment.objects.update_or_create(
            reference="DEMO-PAYSTACK-0001",
            defaults={
                "parent": parent,
                "student_fee": tuition,
                "amount": Decimal("20000.00"),
                "status": Payment.SUCCESS,
                "paid_at": timezone.now(),
            },
        )

        for week, topic in enumerate(
            ["Whole numbers and place value", "Factors and multiples", "Fractions"], start=1
        ):
            note, _ = LessonNote.objects.update_or_create(
                subject=subjects["Mathematics"],
                term=terms[Term.FIRST],
                week_number=week,
                defaults={
                    "topic": topic,
                    "content": f"Class work and homework for week {week}.",
                    "created_by": teacher,
                    "status": PublishStatus.PUBLISHED,
                },
            )
            note.publish()
            note.save()

        LessonNote.objects.update_or_create(
            subject=subjects["English Language"],
            term=terms[Term.FIRST],
            week_number=4,
            defaults={
                "topic": "Comprehension: The market day",
                "content": "Draft passage — not yet shared with students.",
                "created_by": teacher,
                "status": PublishStatus.DRAFT,
            },
        )

        resumption, _ = Announcement.objects.update_or_create(
            title="Resumption notice",
            defaults={
                "body": "All students resume on Monday. Morning assembly starts at 7:45am.",
                "created_by": teacher,
                "school_class": None,
                "status": PublishStatus.PUBLISHED,
            },
        )
        resumption.publish()
        resumption.save()

        Announcement.objects.update_or_create(
            title="PTA meeting (draft)",
            defaults={
                "body": "Draft notice for the PTA meeting.",
                "created_by": teacher,
                "school_class": school_class,
                "status": PublishStatus.DRAFT,
            },
        )

        today = timezone.localdate()
        homework, _ = Assignment.objects.update_or_create(
            title="Mathematics homework: fractions",
            school_class=school_class,
            defaults={
                "due_date": today + timedelta(days=3),
                "kind": "assignment",
                "subject": subjects["Mathematics"],
                "term": terms[Term.FIRST],
                "marks_total": Decimal("20.0"),
                "created_by": teacher,
                "status": PublishStatus.PUBLISHED,
            },
        )
        homework.publish()
        homework.save()

        Assignment.objects.update_or_create(
            title="English composition (draft)",
            school_class=school_class,
            defaults={
                "due_date": today + timedelta(days=5),
                "kind": "coursework",
                "subject": subjects["English Language"],
                "term": terms[Term.FIRST],
                "marks_total": Decimal("30.0"),
                "created_by": teacher,
                "status": PublishStatus.DRAFT,
            },
        )

        for index, student in enumerate(students[:2]):
            if Submission.objects.filter(assignment=homework, student=student).exists():
                continue
            submission = Submission(
                assignment=homework,
                student=student,
                note="Completed exercises 1-10.",
                marks=Decimal("17.50") if index == 0 else None,
                feedback="Neat work." if index == 0 else "",
                graded_by=teacher if index == 0 else None,
                graded_at=timezone.now() if index == 0 else None,
            )
            submission.file.save(
                f"homework-{student.username}.pdf", ContentFile(b"%PDF-1.4 demo"), save=False
            )
            submission.save()

        for offset in range(3):
            day = today - timedelta(days=offset + 1)
            for index, student in enumerate(students):
                status = "absent" if (index + offset) % 7 == 0 else ("late" if index % 5 == 0 else "present")
                Attendance.objects.update_or_create(
                    school_class=school_class,
                    student=student,
                    date=day,
                    defaults={"status": status, "marked_by": teacher},
                )

        Schedule.objects.update_or_create(
            user=students[0],
            name="Mathematics",
            day="Monday",
            defaults={"time": "08:00"},
        )
        Schedule.objects.update_or_create(
            user=students[0],
            name="English Language",
            day="Tuesday",
            defaults={"time": "10:00"},
        )

        self.stdout.write(self.style.SUCCESS("Demo school ready."))
        self.stdout.write(f"  teacher: {TEACHER_USERNAME} / {TEACHER_PASSWORD}  (JSS 2A)")
        self.stdout.write(
            f"  student: {STUDENTS[0][1]} / {settings.DEFAULT_STUDENT_PASSWORD} "
            f"(all {len(students)} imported students share this default password)"
        )
        self.stdout.write(
            f"  parent: {PARENT_USERNAME} / {PARENT_PASSWORD} (wards: {STUDENTS[0][1]}, {STUDENTS[2][1]})"
        )
        student_count = Profile.objects.filter(role=Profile.STUDENT).count()
        self.stdout.write(
            f"  classes: {SchoolClass.objects.count()} | students: {student_count}"
            f" | results: {Result.objects.count()}"
        )
