from tests.conftest import get_test_client


def _query_parameters(path: str) -> dict:
    schema = get_test_client().get("/openapi.json").json()
    parameters = schema["paths"][path]["get"]["parameters"]
    return {parameter["name"]: parameter for parameter in parameters}


def _enum_values(parameter: dict) -> list[str]:
    schema = get_test_client().get("/openapi.json").json()
    parameter_schema = parameter["schema"]
    if "$ref" in parameter_schema:
        component_name = parameter_schema["$ref"].rsplit("/", 1)[-1]
        return schema["components"]["schemas"][component_name]["enum"]
    for option in parameter_schema.get("anyOf", []):
        if "$ref" in option:
            component_name = option["$ref"].rsplit("/", 1)[-1]
            return schema["components"]["schemas"][component_name]["enum"]
    return parameter_schema["enum"]


def test_admin_teacher_section_query_contract_is_exposed_in_openapi() -> None:
    student_params = _query_parameters("/api/v1/admin/students")
    teacher_params = _query_parameters("/api/v1/admin/teachers")
    class_params = _query_parameters("/api/v1/admin/classes")
    slot_params = _query_parameters("/api/v1/admin/teacher-availability/slots")

    assert "assigned_teacher_id" in student_params
    assert student_params["assigned_teacher_id"]["schema"]["anyOf"][0]["format"] == "uuid"
    assert {"account_is_active", "sort_by", "sort_order"} <= teacher_params.keys()
    assert _enum_values(teacher_params["sort_by"]) == [
        "created_at",
        "name",
        "display_name",
        "is_active",
    ]
    assert _enum_values(teacher_params["sort_order"]) == ["asc", "desc"]
    assert teacher_params["sort_by"]["schema"]["default"] == "created_at"
    assert teacher_params["sort_order"]["schema"]["default"] == "desc"
    assert class_params["sort_order"]["schema"]["default"] == "asc"
    assert {"status", "source", "sort_order"} <= slot_params.keys()
    assert _enum_values(slot_params["status"]) == [
        "available",
        "booked",
        "cancelled",
        "blocked",
    ]
    assert _enum_values(slot_params["source"]) == ["rule", "manual"]
    assert slot_params["sort_order"]["schema"]["default"] == "asc"


def test_admin_schedule_and_program_query_contract_is_exposed_in_openapi() -> None:
    class_params = _query_parameters("/api/v1/admin/classes")
    batch_group_params = _query_parameters("/api/v1/admin/batch-groups")
    package_params = _query_parameters("/api/v1/admin/packages")

    assert "q" in class_params
    assert {"q", "is_active", "sort_by", "sort_order"} <= batch_group_params.keys()
    assert _enum_values(batch_group_params["sort_by"]) == [
        "created_at",
        "name",
        "active_member_count",
        "upcoming_scheduled_count",
        "is_active",
    ]
    assert batch_group_params["sort_by"]["schema"]["default"] == "created_at"
    assert batch_group_params["sort_order"]["schema"]["default"] == "desc"
    assert {"q", "is_active", "sort_by", "sort_order"} <= package_params.keys()
    assert _enum_values(package_params["sort_by"]) == [
        "created_at",
        "name",
        "duration_days",
        "price_amount",
        "is_active",
    ]

    schema = get_test_client().get("/openapi.json").json()
    paths = schema["paths"]
    assert "get" in paths["/api/v1/admin/classes/{class_session_id}/roster"]
    assert "get" in paths["/api/v1/admin/classes/{class_session_id}/activity"]
    assert "post" in paths["/api/v1/admin/bookings/one-on-one"]
    assert "post" in paths["/api/v1/admin/batch-groups"]
    assert "post" in paths["/api/v1/admin/batch-groups/{batch_group_id}/students"]
    assert "delete" in paths[
        "/api/v1/admin/batch-groups/{batch_group_id}/students/{student_id}"
    ]
    assert "post" in paths["/api/v1/admin/packages"]
    assert "post" in paths[
        "/api/v1/admin/classes/{class_session_id}/reschedule/one-on-one"
    ]
    assert "post" in paths["/api/v1/admin/classes/{class_session_id}/reschedule/batch"]


def test_batch_schedule_day_contract_is_exposed_in_openapi() -> None:
    schema = get_test_client().get("/openapi.json").json()
    paths = schema["paths"]

    assert {"get", "patch"} <= paths["/api/v1/admin/batch-schedule-defaults"].keys()
    assert {"get", "post"} <= paths["/api/v1/admin/batch-schedule-days"].keys()
    assert "post" in paths["/api/v1/admin/batch-schedule-days/bulk"]
    assert "post" in paths["/api/v1/admin/batch-schedule-days/cancel-bulk"]
    assert "get" in paths["/api/v1/admin/batch-schedule-days/{day_id}"]
    assert "post" in paths["/api/v1/admin/batch-schedule-days/{day_id}/cancel"]
    assert "post" in paths["/api/v1/admin/batch-schedule-days/{day_id}/options"]
    assert {"patch", "delete"} <= paths[
        "/api/v1/admin/batch-schedule-days/{day_id}/options/{class_session_id}"
    ].keys()
    assert {"put", "delete"} <= paths[
        "/api/v1/admin/batch-schedule-days/{day_id}/students/{student_id}"
    ].keys()
    assert "get" in paths["/api/v1/students/{student_id}/batch-schedule-days"]
    assert "put" in paths[
        "/api/v1/students/{student_id}/batch-schedule-days/{day_id}/selection"
    ]

    create_schema = schema["components"]["schemas"]["BatchDayCreate"]
    assert create_schema["properties"]["schedule_date"]["format"] == "date"
    defaults_schema = schema["components"]["schemas"]["BatchScheduleDefaultsRead"]
    assert defaults_schema["properties"]["timezone"]["type"] == "string"
    defaults_update = schema["components"]["schemas"]["BatchScheduleDefaultsUpdate"]
    assert "timezone" not in defaults_update["properties"]


def test_batch_group_package_contract_is_exposed_in_openapi() -> None:
    schema = get_test_client().get("/openapi.json").json()
    schemas = schema["components"]["schemas"]

    assert "package_id" in schemas["BatchGroupCreate"]["properties"]
    assert "package_id" in schemas["BatchGroupUpdate"]["properties"]
    assert "package_id" in schemas["BatchGroupRead"]["properties"]
    assert "package" in schemas["BatchGroupRead"]["properties"]
    assert "package" in schemas["AdminBatchGroupRead"]["properties"]
    assert "allow_package_access_override" in schemas[
        "StudentBatchMembershipAssign"
    ]["properties"]
    assert "allow_package_access_override" in schemas[
        "AdminStudentBatchGroupSet"
    ]["properties"]
