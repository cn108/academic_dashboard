"""Domain models for a Nigerian primary/secondary school.

The system is deliberately class-centric: a teacher manages one class of 10-50
students, teaches subjects inside it, and publishes (or withholds) lesson notes,
results, assignments and announcements. Students only ever see published work for
their own class.
"""

from datetime import time
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

MIN_CLASS_SIZE = 10
MAX_CLASS_SIZE = 50

# WAEC-style grading, evaluated top to bottom: (minimum total, letter, remark)
GRADE_SCALE = (
    (70, "A", "Excellent"),
    (60, "B", "Very good"),
    (50, "C", "Good"),
    (45, "D", "Fair"),
    (40, "E", "Pass"),
)
FAILING_LETTER = "F"
FAILING_REMARK = "Fail"

CA_MAX = {"ca1": 10, "ca2": 10, "ca3": 20}
CA_TOTAL_MAX = sum(CA_MAX.values())
EXAM_MAX = 60


class PublishStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class Publishable(models.Model):
    """Anything teachers create and then choose to show (or not show) students."""

    status = models.CharField(max_length=10, choices=PublishStatus.choices, default=PublishStatus.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def is_published(self):
        return self.status == PublishStatus.PUBLISHED

    def publish(self):
        self.status = PublishStatus.PUBLISHED
        self.published_at = timezone.now()

    def save(self, *args, **kwargs):
        if self.is_published and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)


class Profile(models.Model):
    """The portal a user sees plus the student's school identity."""

    STUDENT = "student"
    TEACHER = "teacher"
    PARENT = "parent"
    ROLE_CHOICES = [(STUDENT, "Student"), (TEACHER, "Teacher"), (PARENT, "Parent / guardian")]

    MALE = "M"
    FEMALE = "F"
    GENDER_CHOICES = [(MALE, "Male"), (FEMALE, "Female")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=STUDENT)
    admission_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    school_class = models.ForeignKey(
        "SchoolClass",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="students",
    )
    must_change_password = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.get_username()} ({self.role})"

    @property
    def is_teacher(self):
        return self.role == self.TEACHER


def role_of(user):
    """Resolve a user's role without requiring a Profile row to exist yet."""
    if not user or not user.is_authenticated:
        return None
    if user.is_staff:
        return Profile.TEACHER
    profile, _created = Profile.objects.get_or_create(user=user)
    return profile.role


def is_teacher(user):
    return role_of(user) == Profile.TEACHER


def is_student(user):
    return role_of(user) == Profile.STUDENT


def is_parent(user):
    return role_of(user) == Profile.PARENT


class AcademicSession(models.Model):
    """A school year, e.g. 2025/2026."""

    name = models.CharField(max_length=20, unique=True, help_text="e.g. 2025/2026")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            AcademicSession.objects.exclude(pk=self.pk).update(is_current=False)


class Term(models.Model):
    FIRST = "First Term"
    SECOND = "Second Term"
    THIRD = "Third Term"
    NAME_CHOICES = [(FIRST, FIRST), (SECOND, SECOND), (THIRD, THIRD)]

    session = models.ForeignKey(AcademicSession, on_delete=models.CASCADE, related_name="terms")
    name = models.CharField(max_length=20, choices=NAME_CHOICES)
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["session__name", "name"]
        constraints = [models.UniqueConstraint(fields=["session", "name"], name="unique_term_per_session")]

    def __str__(self):
        return f"{self.session.name} — {self.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            Term.objects.exclude(pk=self.pk).update(is_current=False)

    @classmethod
    def current(cls):
        return cls.objects.filter(is_current=True).select_related("session").first()


class SchoolClass(models.Model):
    """A class arm a teacher manages, e.g. JSS 2A."""

    LEVEL_CHOICES = [
        ("Primary 1", "Primary 1"),
        ("Primary 2", "Primary 2"),
        ("Primary 3", "Primary 3"),
        ("Primary 4", "Primary 4"),
        ("Primary 5", "Primary 5"),
        ("Primary 6", "Primary 6"),
        ("JSS 1", "JSS 1"),
        ("JSS 2", "JSS 2"),
        ("JSS 3", "JSS 3"),
        ("SS 1", "SS 1"),
        ("SS 2", "SS 2"),
        ("SS 3", "SS 3"),
    ]

    name = models.CharField(max_length=30, unique=True, help_text="e.g. JSS 2A")
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES)
    class_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="classes_managed",
    )
    capacity = models.PositiveSmallIntegerField(
        default=MAX_CLASS_SIZE,
        validators=[MinValueValidator(MIN_CLASS_SIZE), MaxValueValidator(MAX_CLASS_SIZE)],
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "school classes"

    def __str__(self):
        return self.name

    @property
    def student_count(self):
        return self.students.count()

    @property
    def is_full(self):
        return self.student_count >= self.capacity

    def can_manage(self, user):
        if not user or not user.is_authenticated:
            return False
        return bool(user.is_staff or self.class_teacher_id == user.pk)


class Subject(models.Model):
    """A subject taught to one class by one teacher."""

    name = models.CharField(max_length=100)
    # Nullable only so the pivot migration can adopt the legacy table; the API
    # and admin both require a class.
    school_class = models.ForeignKey(
        SchoolClass, null=True, on_delete=models.CASCADE, related_name="subjects"
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="subjects_taught",
    )

    class Meta:
        ordering = ["school_class__name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["school_class", "name"], name="unique_subject_per_class")
        ]

    def __str__(self):
        return f"{self.name} ({self.school_class.name})"

    def can_manage(self, user):
        if not user or not user.is_authenticated:
            return False
        return bool(
            user.is_staff or self.teacher_id == user.pk or self.school_class.class_teacher_id == user.pk
        )


class Result(Publishable):
    """A student's score in one subject for one term."""

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="results")
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="results")
    session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name="results")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="results")
    ca1 = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(CA_MAX["ca1"])])
    ca2 = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(CA_MAX["ca2"])])
    ca3 = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(CA_MAX["ca3"])])
    exam = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(EXAM_MAX)])
    total = models.PositiveSmallIntegerField(default=0, editable=False)
    grade = models.CharField(max_length=1, blank=True, editable=False)
    remarks = models.CharField(max_length=20, blank=True, editable=False)
    teacher_remark = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="results_entered",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["subject__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "subject", "session", "term"],
                name="unique_result_per_term",
            )
        ]

    def __str__(self):
        return f"{self.student.get_username()} {self.subject.name}: {self.total}"

    @property
    def ca_total(self):
        return self.ca1 + self.ca2 + self.ca3

    @staticmethod
    def grade_for(total):
        """Return (letter, remark) for a 0-100 total."""
        for threshold, letter, remark in GRADE_SCALE:
            if total >= threshold:
                return letter, remark
        return FAILING_LETTER, FAILING_REMARK

    def compute(self):
        ca_total = self.ca_total
        if ca_total > CA_TOTAL_MAX:
            raise ValidationError(f"Continuous assessment cannot exceed {CA_TOTAL_MAX}.")
        if self.exam > EXAM_MAX:
            raise ValidationError(f"Exam score cannot exceed {EXAM_MAX}.")
        self.total = ca_total + self.exam
        self.grade, self.remarks = self.grade_for(self.total)

    def clean(self):
        for field, maximum in CA_MAX.items():
            if getattr(self, field) > maximum:
                raise ValidationError({field: f"Cannot exceed {maximum}."})
        if self.exam > EXAM_MAX:
            raise ValidationError({"exam": f"Cannot exceed {EXAM_MAX}."})
        if self.term_id and self.session_id and self.term.session_id != self.session_id:
            raise ValidationError({"term": "The term does not belong to the chosen session."})

    def save(self, *args, **kwargs):
        self.compute()
        super().save(*args, **kwargs)


class LessonNote(Publishable):
    """Weekly lesson content a teacher writes for a subject."""

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="lesson_notes")
    term = models.ForeignKey(
        Term, null=True, blank=True, on_delete=models.SET_NULL, related_name="lesson_notes"
    )
    week_number = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(13)])
    topic = models.CharField(max_length=200)
    content = models.TextField(blank=True)
    attachment = models.FileField(upload_to="lesson-notes/%Y/%m/", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="lesson_notes_created",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["subject__name", "week_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "term", "week_number"],
                name="unique_lesson_note_per_week",
            )
        ]

    def __str__(self):
        return f"Week {self.week_number}: {self.topic}"


class Announcement(Publishable):
    """A notice for the whole school (no class) or for one class."""

    title = models.CharField(max_length=200)
    body = models.TextField()
    school_class = models.ForeignKey(
        SchoolClass,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="announcements",
        help_text="Leave empty to address the whole school.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="announcements_created",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def audience(self):
        return self.school_class.name if self.school_class_id else "Whole school"


class Assignment(Publishable):
    KIND_CHOICES = [
        ("assignment", "Assignment"),
        ("coursework", "Coursework"),
        ("group_project", "Group project"),
    ]

    title = models.CharField(max_length=255)
    due_date = models.DateField()
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="assignment")
    subject = models.ForeignKey(
        Subject, null=True, blank=True, on_delete=models.SET_NULL, related_name="assignments"
    )
    school_class = models.ForeignKey(
        SchoolClass,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assignments",
    )
    term = models.ForeignKey(
        Term, null=True, blank=True, on_delete=models.SET_NULL, related_name="assignments"
    )
    marks_total = models.DecimalField(max_digits=5, decimal_places=1, default=100)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assignments_created",
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["due_date", "title"]
        indexes = [models.Index(fields=["school_class", "status"], name="assignment_class_status_idx")]

    def __str__(self):
        return f"{self.title} (due {self.due_date})"

    @property
    def is_overdue(self):
        return self.due_date < timezone.localdate()


class Submission(models.Model):
    """A student's uploaded work for an assignment, and its marking."""

    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name="submissions")
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions"
    )
    file = models.FileField(upload_to="submissions/%Y/%m/")
    note = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="graded_submissions",
    )
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        constraints = [
            models.UniqueConstraint(fields=["assignment", "student"], name="unique_submission_per_student")
        ]

    def __str__(self):
        return f"{self.student} → {self.assignment} ({self.submitted_at:%Y-%m-%d})"

    @property
    def is_graded(self):
        return self.marks is not None


class Attendance(models.Model):
    PRESENT = "present"
    LATE = "late"
    ABSENT = "absent"
    STATUS_CHOICES = [(PRESENT, "Present"), (LATE, "Late"), (ABSENT, "Absent")]

    school_class = models.ForeignKey(
        SchoolClass,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="attendance",
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attendance")
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PRESENT)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="marked_attendance",
    )

    class Meta:
        ordering = ["-date", "student__username"]
        constraints = [
            models.UniqueConstraint(
                fields=["school_class", "student", "date"], name="unique_attendance_per_day"
            )
        ]
        indexes = [models.Index(fields=["school_class", "date"], name="attendance_class_date_idx")]

    def __str__(self):
        return f"{self.student} {self.school_class.name} {self.date}: {self.status}"


class Schedule(models.Model):
    """A student's personal timetable entry."""

    DAYS = [
        ("Monday", "Monday"),
        ("Tuesday", "Tuesday"),
        ("Wednesday", "Wednesday"),
        ("Thursday", "Thursday"),
        ("Friday", "Friday"),
        ("Saturday", "Saturday"),
        ("Sunday", "Sunday"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    name = models.CharField(max_length=255)
    day = models.CharField(max_length=10, choices=DAYS)
    time = models.TimeField(default=time(8, 0))

    class Meta:
        ordering = ["day", "time"]
        indexes = [models.Index(fields=["user", "day"], name="schedule_user_day_idx")]

    def __str__(self):
        return f"{self.name} on {self.day} at {self.time}"


class ParentStudentLink(models.Model):
    """A guardian's link to one of their wards.

    A parent account can be linked to several children (and a child can have a
    father, mother and guardian), which is what makes the parent portal useful.
    """

    FATHER = "father"
    MOTHER = "mother"
    GUARDIAN = "guardian"
    RELATIONSHIP_CHOICES = [
        (FATHER, "Father"),
        (MOTHER, "Mother"),
        (GUARDIAN, "Guardian"),
    ]

    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wards",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="guardians",
    )
    relationship = models.CharField(max_length=20, choices=RELATIONSHIP_CHOICES, default=GUARDIAN)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["student__first_name", "student__username"]
        constraints = [models.UniqueConstraint(fields=["parent", "student"], name="unique_parent_student")]

    def __str__(self):
        return f"{self.parent.get_username()} → {self.student.get_username()} ({self.relationship})"


class Fee(models.Model):
    """A school bill for one class level in one term, e.g. JSS 2 tuition."""

    session = models.ForeignKey(AcademicSession, on_delete=models.PROTECT, related_name="fees")
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="fees")
    class_level = models.CharField(max_length=20, choices=SchoolClass.LEVEL_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    description = models.CharField(max_length=200, help_text="e.g. Tuition and levies")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["session__name", "term__name", "class_level", "description"]

    def __str__(self):
        return f"{self.class_level} {self.term.name}: {self.description}"

    def clean(self):
        if self.term_id and self.session_id and self.term.session_id != self.session_id:
            raise ValidationError({"term": "The term does not belong to the chosen session."})


class StudentFee(models.Model):
    """One student's share of a fee, with what they have paid so far."""

    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"
    STATUS_CHOICES = [(UNPAID, "Unpaid"), (PARTIAL, "Part payment"), (PAID, "Paid")]

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_fees"
    )
    fee = models.ForeignKey(Fee, on_delete=models.CASCADE, related_name="student_fees")
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0, editable=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=UNPAID)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["student__first_name", "fee__description"]
        constraints = [models.UniqueConstraint(fields=["student", "fee"], name="unique_student_fee")]

    def __str__(self):
        return f"{self.student.get_username()} {self.fee.description}: {self.status}"

    @property
    def amount(self):
        return self.fee.amount

    def recompute(self):
        """Derive the balance and status from the fee and what has been paid."""
        outstanding = self.fee.amount - self.amount_paid
        self.balance = max(outstanding, Decimal("0.00"))
        if self.amount_paid <= 0:
            self.status = self.UNPAID
        elif self.balance <= 0:
            self.status = self.PAID
        else:
            self.status = self.PARTIAL

    def save(self, *args, **kwargs):
        self.recompute()
        super().save(*args, **kwargs)


class Payment(models.Model):
    """A Paystack transaction against one student fee."""

    PAYSTACK = "paystack"
    GATEWAY_CHOICES = [(PAYSTACK, "Paystack")]

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    STATUS_CHOICES = [(PENDING, "Pending"), (SUCCESS, "Successful"), (FAILED, "Failed")]

    parent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments")
    student_fee = models.ForeignKey(StudentFee, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=64, unique=True)
    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES, default=PAYSTACK)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "reference"], name="payment_status_ref_idx")]

    def __str__(self):
        return f"{self.reference} {self.amount} ({self.status})"
