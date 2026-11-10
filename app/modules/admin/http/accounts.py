from uuid import UUID

from fastapi import APIRouter, Response, status
from pydantic import EmailStr

from app.api.deps import DBSession, Pagination
from app.core.pagination import Page
from app.modules.admin.http.types import (
    IsActiveQuery,
    ProgramTypeQuery,
    SearchQuery,
    SortOrderQuery,
    StudentAccessStateQuery,
    StudentSortByQuery,
    StudentStatusQuery,
    TeacherIdQuery,
    TeacherSortByQuery,
)
from app.modules.admin.schemas import (
    AdminStudentAccessGrantCreate,
    AdminStudentAccessGrantRead,
    AdminStudentBatchGroupSet,
    AdminStudentCreate,
    AdminStudentPaymentCreate,
    AdminStudentPaymentRead,
    AdminStudentPaymentUpdate,
    AdminStudentRead,
    AdminStudentSortBy,
    AdminStudentUpdate,
    AdminTeacherCreate,
    AdminTeacherLinkRead,
    AdminTeacherLinkRequest,
    AdminTeacherRead,
    AdminTeacherSortBy,
    AdminUserLookupRead,
    SortOrder,
)
from app.modules.auth.dependencies import CurrentUser
from app.modules.batch_groups.schemas import (
    StudentBatchMembershipRead,
)
from app.modules.read_models.services import (
    AdminAccountWorkflow,
    AdminSchedulingService,
    AdminStudentWorkflowService,
)
from app.modules.students.schemas import StudentProgramChangeRead, StudentProgramSwitch
from app.modules.teachers.schemas import TeacherUpdate
from app.modules.users.schemas import UserRead, UserRolesUpdate, UserUpdate
from app.modules.users.service import UserService

router = APIRouter()


@router.get("/users/lookup", response_model=AdminUserLookupRead)
async def lookup_user(email: EmailStr, session: DBSession) -> AdminUserLookupRead:
    return await AdminAccountWorkflow(session).lookup_user(str(email))


@router.post("/teachers/link-existing", response_model=AdminTeacherLinkRead)
async def link_existing_admin(
    body: AdminTeacherLinkRequest, session: DBSession
) -> AdminTeacherLinkRead:
    return await AdminAccountWorkflow(session).link_existing_admin(body)


@router.put("/users/{user_id}/roles", response_model=UserRead)
async def set_user_roles(
    user_id: UUID, body: UserRolesUpdate, session: DBSession, actor: CurrentUser
) -> UserRead:
    return await UserService(session).set_roles(user_id, body.roles, actor.id)


@router.get("/students", response_model=Page[AdminStudentRead])
async def list_students(
    session: DBSession,
    pagination: Pagination,
    q: SearchQuery = None,
    status: StudentStatusQuery = None,
    program_type: ProgramTypeQuery = None,
    access_state: StudentAccessStateQuery = None,
    batch_group_id: UUID | None = None,
    assigned_teacher_id: TeacherIdQuery = None,
    sort_by: StudentSortByQuery = AdminStudentSortBy.CREATED_AT,
    sort_order: SortOrderQuery = SortOrder.DESC,
) -> Page[AdminStudentRead]:
    return await AdminAccountWorkflow(session).list_students(
        pagination,
        q=q,
        status=status,
        program_type=program_type,
        access_state=access_state,
        batch_group_id=batch_group_id,
        assigned_teacher_id=assigned_teacher_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.patch("/users/{user_id}", response_model=UserRead)
async def update_user(
    user_id: UUID,
    user_in: UserUpdate,
    session: DBSession,
) -> UserRead:
    return await AdminSchedulingService(session).update_user(user_id, user_in)


@router.post("/teachers", response_model=AdminTeacherRead, status_code=status.HTTP_201_CREATED)
async def create_teacher(
    teacher_in: AdminTeacherCreate,
    session: DBSession,
) -> AdminTeacherRead:
    user, teacher = await AdminAccountWorkflow(session).create_teacher(teacher_in)
    return AdminTeacherRead(user=user, teacher=teacher)


@router.get("/teachers", response_model=Page[AdminTeacherRead])
async def list_teachers(
    session: DBSession,
    pagination: Pagination,
    q: SearchQuery = None,
    is_active: IsActiveQuery = None,
    account_is_active: IsActiveQuery = None,
    sort_by: TeacherSortByQuery = AdminTeacherSortBy.CREATED_AT,
    sort_order: SortOrderQuery = SortOrder.DESC,
) -> Page[AdminTeacherRead]:
    return await AdminAccountWorkflow(session).list_teachers(
        pagination,
        q=q,
        is_active=is_active,
        account_is_active=account_is_active,
        sort_by=sort_by,
        sort_order=sort_order,
    )


@router.get("/teachers/{teacher_id}", response_model=AdminTeacherRead)
async def get_teacher(
    teacher_id: UUID,
    session: DBSession,
) -> AdminTeacherRead:
    return await AdminAccountWorkflow(session).get_teacher(teacher_id)


@router.patch("/teachers/{teacher_id}", response_model=AdminTeacherRead)
async def update_teacher(
    teacher_id: UUID,
    teacher_in: TeacherUpdate,
    session: DBSession,
) -> AdminTeacherRead:
    return await AdminAccountWorkflow(session).update_teacher(teacher_id, teacher_in)


@router.post("/students", response_model=AdminStudentRead, status_code=status.HTTP_201_CREATED)
async def create_student(
    student_in: AdminStudentCreate,
    session: DBSession,
) -> AdminStudentRead:
    user, student = await AdminAccountWorkflow(session).create_student(student_in)
    return AdminStudentRead(user=user, student=student)


@router.get("/students/{student_id}", response_model=AdminStudentRead)
async def get_student(
    student_id: UUID,
    session: DBSession,
) -> AdminStudentRead:
    return await AdminAccountWorkflow(session).get_student(student_id)


@router.patch("/students/{student_id}", response_model=AdminStudentRead)
async def update_student(
    student_id: UUID,
    student_in: AdminStudentUpdate,
    session: DBSession,
) -> AdminStudentRead:
    return await AdminAccountWorkflow(session).update_student(student_id, student_in)


@router.get("/students/{student_id}/payments", response_model=Page[AdminStudentPaymentRead])
async def list_student_payments(
    student_id: UUID,
    session: DBSession,
    pagination: Pagination,
) -> Page[AdminStudentPaymentRead]:
    return await AdminStudentWorkflowService(session).list_student_payments(student_id, pagination)


@router.post(
    "/students/{student_id}/payments",
    response_model=AdminStudentPaymentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_student_payment(
    student_id: UUID,
    payment_in: AdminStudentPaymentCreate,
    session: DBSession,
) -> AdminStudentPaymentRead:
    return await AdminStudentWorkflowService(session).create_student_payment(student_id, payment_in)


@router.patch(
    "/students/{student_id}/payments/{payment_id}",
    response_model=AdminStudentPaymentRead,
)
async def update_student_payment(
    student_id: UUID,
    payment_id: UUID,
    payment_in: AdminStudentPaymentUpdate,
    session: DBSession,
) -> AdminStudentPaymentRead:
    return await AdminStudentWorkflowService(session).update_student_payment(
        student_id,
        payment_id,
        payment_in,
    )


@router.delete(
    "/students/{student_id}/payments/{payment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_student_payment(
    student_id: UUID,
    payment_id: UUID,
    session: DBSession,
) -> Response:
    await AdminStudentWorkflowService(session).delete_student_payment(student_id, payment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/students/{student_id}/access-grants",
    response_model=Page[AdminStudentAccessGrantRead],
)
async def list_student_access_grants(
    student_id: UUID,
    session: DBSession,
    pagination: Pagination,
) -> Page[AdminStudentAccessGrantRead]:
    return await AdminStudentWorkflowService(session).list_student_access_grants(
        student_id, pagination
    )


@router.post(
    "/students/{student_id}/access-grants",
    response_model=AdminStudentAccessGrantRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_student_access_grant(
    student_id: UUID,
    grant_in: AdminStudentAccessGrantCreate,
    session: DBSession,
) -> AdminStudentAccessGrantRead:
    return await AdminStudentWorkflowService(session).create_student_access_grant(
        student_id, grant_in
    )


@router.post(
    "/students/{student_id}/program-switch",
    response_model=StudentProgramChangeRead,
)
async def switch_student_program(
    student_id: UUID,
    switch_in: StudentProgramSwitch,
    session: DBSession,
) -> StudentProgramChangeRead:
    return await AdminStudentWorkflowService(session).switch_student_program(student_id, switch_in)


@router.post(
    "/students/{student_id}/batch-group",
    response_model=StudentBatchMembershipRead,
)
async def set_student_batch_group(
    student_id: UUID,
    batch_group_in: AdminStudentBatchGroupSet,
    session: DBSession,
) -> StudentBatchMembershipRead:
    return await AdminStudentWorkflowService(session).set_student_batch_group(
        student_id, batch_group_in
    )


@router.get(
    "/students/{student_id}/batch-memberships",
    response_model=Page[StudentBatchMembershipRead],
)
async def list_student_batch_memberships(
    student_id: UUID,
    session: DBSession,
    pagination: Pagination,
) -> Page[StudentBatchMembershipRead]:
    return await AdminStudentWorkflowService(session).list_student_batch_memberships(
        student_id, pagination
    )
