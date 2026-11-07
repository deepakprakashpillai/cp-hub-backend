from tests.conftest import get_test_client


def _response_ref(schema: dict, path: str, method: str = "get") -> str:
    response = schema["paths"][path][method]["responses"]["200"]["content"]["application/json"]
    return response["schema"]["$ref"].rsplit("/", 1)[-1]


def test_portal_identity_and_projection_contracts_are_exposed() -> None:
    schema = get_test_client().get("/openapi.json").json()
    schemas = schema["components"]["schemas"]

    assert _response_ref(schema, "/api/v1/teacher/me") == "AdminTeacherRead"
    assert _response_ref(schema, "/api/v1/student/me") == "AdminStudentRead"
    assert _response_ref(schema, "/api/v1/teacher/me/classes").startswith(
        "Page_TeacherClassSessionRead"
    )
    assert _response_ref(schema, "/api/v1/teacher/me/classes/{class_session_id}") == (
        "TeacherClassSessionRead"
    )
    assert _response_ref(schema, "/api/v1/teacher/me/classes/{class_session_id}/roster").startswith(
        "Page_AdminClassRosterBookingRead"
    )
    assert _response_ref(schema, "/api/v1/teacher/me/students").startswith("Page_AdminStudentRead")
    assert _response_ref(schema, "/api/v1/student/me/bookings").startswith(
        "Page_StudentBookingRead"
    )
    assert _response_ref(schema, "/api/v1/student/me/bookings/{booking_id}") == "StudentBookingRead"
    assert _response_ref(schema, "/api/v1/student/me/available-slots").startswith(
        "Page_StudentTeacherSlotRead"
    )

    assert "booking_status_counts" in schemas["TeacherClassSessionRead"]["properties"]
    assert "student" in schemas["AdminClassRosterBookingRead"]["properties"]
    assert "class_session" in schemas["StudentBookingRead"]["properties"]
    assert "teacher" in schemas["StudentTeacherSlotRead"]["properties"]


def test_portal_filter_and_array_contracts_are_exposed() -> None:
    schema = get_test_client().get("/openapi.json").json()
    paths = schema["paths"]

    teacher_parameters = {
        parameter["name"] for parameter in paths["/api/v1/teacher/me/classes"]["get"]["parameters"]
    }
    student_parameters = {
        parameter["name"] for parameter in paths["/api/v1/student/me/bookings"]["get"]["parameters"]
    }
    assert {
        "program_type",
        "status",
        "sort_order",
        "starts_from",
        "starts_to",
    } <= teacher_parameters
    assert {"status", "starts_from", "starts_to"} <= student_parameters

    batch_schema = paths["/api/v1/student/me/batch-schedule-days"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    feedback_schema = paths["/api/v1/student/me/feedbacks"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    assert batch_schema["type"] == "array"
    assert feedback_schema["type"] == "array"
    attendance_ref = paths["/api/v1/teacher/me/classes/{class_session_id}/attendance"]["post"][
        "requestBody"
    ]["content"]["application/json"]["schema"]["$ref"]
    assert attendance_ref.endswith("/ClassAttendanceMark")
    schedule_ref = paths["/api/v1/teacher/me/classes/{class_session_id}/schedule"]["patch"][
        "requestBody"
    ]["content"]["application/json"]["schema"]["$ref"]
    cancel_ref = paths["/api/v1/teacher/me/classes/{class_session_id}/cancel"]["post"][
        "requestBody"
    ]["content"]["application/json"]["schema"]["$ref"]
    assert schedule_ref.endswith("/TeacherClassScheduleUpdate")
    assert cancel_ref.endswith("/TeacherClassCancel")
