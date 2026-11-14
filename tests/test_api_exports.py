"""Excel download of the class broadsheet."""

from io import BytesIO

from openpyxl import load_workbook

from core.models import PublishStatus, Result, Subject


def add_result(student, subject, session, term, exam, status=PublishStatus.PUBLISHED):
    return Result.objects.create(
        student=student,
        subject=subject,
        session=session,
        term=term,
        ca1=8,
        ca2=9,
        ca3=11,
        exam=exam,
        status=status,
    )


def broadsheet_url(school_class, session, term, fmt="xlsx"):
    return f"/api/classes/{school_class.pk}/broadsheet/?session={session.pk}&term={term.pk}&format={fmt}"


def test_broadsheet_downloads_a_formatted_workbook(
    teacher_client, school_class, subject, teacher, student, classmate, session, term
):
    english = Subject.objects.create(name="English Language", school_class=school_class, teacher=teacher)
    # Chidera: Maths 58, English 70. Emeka: Maths 82, English 50.
    add_result(student, subject, session, term, exam=30)
    add_result(student, english, session, term, exam=42)
    add_result(classmate, subject, session, term, exam=54)
    add_result(classmate, english, session, term, exam=22)

    response = teacher_client.get(broadsheet_url(school_class, session, term))

    assert response.status_code == 200
    assert response["Content-Type"] == ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    disposition = response["Content-Disposition"]
    assert disposition.startswith('attachment; filename="broadsheet-jss-2a-')
    assert disposition.endswith('.xlsx"')

    sheet = load_workbook(BytesIO(response.content)).active
    assert sheet.title == "Broadsheet"
    assert "JSS 2A broadsheet" in sheet["A1"].value
    assert "First Term" in sheet["A1"].value

    headers = [sheet.cell(row=4, column=column).value for column in range(1, 8)]
    assert headers == [
        "Student",
        "Admission No",
        "English Language",
        "Mathematics",
        "Total",
        "Average",
        "Position",
    ]

    rows = {}
    for row in (5, 6):
        values = [sheet.cell(row=row, column=column).value for column in range(1, 8)]
        rows[values[1]] = values
    assert rows["JSS2A-001"] == ["Chidera Okafor", "JSS2A-001", 70, 58, 128, 64, 2]
    assert rows["JSS2A-002"] == ["Emeka Nwosu", "JSS2A-002", 50, 82, 132, 66, 1]

    class_average = [sheet.cell(row=7, column=column).value for column in range(1, 8)]
    # openpyxl stores an empty string as a blank cell, which reads back as None.
    assert class_average == ["Class Average", None, 60, 70, None, 65, None]


def test_broadsheet_xlsx_ignores_draft_results(teacher_client, school_class, subject, student, session, term):
    add_result(student, subject, session, term, exam=60, status=PublishStatus.DRAFT)

    response = teacher_client.get(broadsheet_url(school_class, session, term))

    sheet = load_workbook(BytesIO(response.content)).active
    assert sheet.cell(row=5, column=1).value == "Chidera Okafor"
    # One subject, so: 3 = Mathematics, 4 = Total, 5 = Average, 6 = Position.
    assert sheet.cell(row=5, column=3).value is None
    assert sheet.cell(row=5, column=4).value == 0
    assert sheet.cell(row=7, column=3).value is None


def test_another_class_teacher_cannot_export(school_class, other_teacher_client, session, term):
    # The viewset scopes classes to their teacher, so it is not even visible.
    response = other_teacher_client.get(broadsheet_url(school_class, session, term))
    assert response.status_code == 404


def test_student_cannot_export_the_class_broadsheet(student_client, school_class, session, term):
    response = student_client.get(broadsheet_url(school_class, session, term))
    assert response.status_code == 403
