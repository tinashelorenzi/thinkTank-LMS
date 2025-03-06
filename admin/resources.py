import datetime
from typing import List

from fastapi_admin.resources import Field, Link, Model, Action
from fastapi_admin.widgets import displays, inputs
from fastapi_admin.enums import Method

from models import (
    User, Course, Section, Enrollment, Assignment, Submission,
    Grade, Module, Discussion, File, Quiz, Question
)
from models.user import UserRole


# Base model resource with common fields
class BaseResource(Model):
    """Base resource for all models with created/updated timestamps"""
    created_at = Field(
        label="Created At",
        display=displays.DatetimeDisplay(),
        input_=inputs.DatetimeInput(),
        searchable=True,
    )
    updated_at = Field(
        label="Updated At",
        display=displays.DatetimeDisplay(),
        input_=inputs.DatetimeInput(),
        searchable=True,
    )


# User resource
class UserResource(BaseResource):
    label = "Users"
    model = User
    page_pre_title = "users"
    page_title = "User Management"
    filters = [
        "username",
        "email",
        "role",
        "is_active",
    ]
    fields = [
        "id",
        Field(
            name="username",
            label="Username",
            display=displays.TextDisplay(),
            input_=inputs.TextInput(),
            searchable=True,
        ),
        Field(
            name="email",
            label="Email",
            display=displays.TextDisplay(),
            input_=inputs.TextInput(),
            searchable=True,
        ),
        Field(
            name="first_name",
            label="First Name",
            display=displays.TextDisplay(),
            input_=inputs.TextInput(),
            searchable=True,
        ),
        Field(
            name="last_name",
            label="Last Name",
            display=displays.TextDisplay(),
            input_=inputs.TextInput(),
            searchable=True,
        ),
        Field(
            name="role",
            label="Role",
            display=displays.EnumDisplay(enum=UserRole),
            input_=inputs.EnumSelect(enum=UserRole),
            searchable=True,
        ),
        Field(
            name="is_active",
            label="Active",
            display=displays.BooleanDisplay(),
            input_=inputs.BooleanInput(),
        ),
        Field(
            name="is_verified",
            label="Email Verified",
            display=displays.BooleanDisplay(),
            input_=inputs.BooleanInput(),
        ),
        Field(
            name="last_login",
            label="Last Login",
            display=displays.DatetimeDisplay(),
            input_=inputs.DatetimeInput(),
        ),
        "created_at",
        "updated_at",
    ]
    
    async def cell_attributes(self, request, obj, field):
        if field == "is_active" and not obj.is_active:
            return {"class": "bg-warning"}
        return await super().cell_attributes(request, obj, field)
    
    async def get_actions(self, request) -> List[Action]:
        actions = await super().get_actions(request)
        actions.append(
            Action(
                name="activate",
                label="Activate Users",
                icon="ti ti-check",
                method=Method.PUT,
                ajax=True,
            )
        )
        actions.append(
            Action(
                name="deactivate",
                label="Deactivate Users",
                icon="ti ti-x",
                method=Method.PUT,
                ajax=True,
                confirm="Are you sure you want to deactivate the selected users?",
            )
        )
        return actions
    
    async def activate(self, request, pk):
        """Activate a user"""
        user = await self.model.get_or_none(pk=pk)
        if user:
            user.is_active = True
            await user.save()
        return {"success": True}
    
    async def deactivate(self, request, pk):
        """Deactivate a user"""
        user = await self.model.get_or_none(pk=pk)
        if user:
            user.is_active = False
            await user.save()
        return {"success": True}


# Course resource
class CourseResource(BaseResource):
    label = "Courses"
    model = Course
    page_pre_title = "courses"
    page_title = "Course Management"
    filters = [
        "name",
        "code",
        "state",
        "visibility",
    ]
    fields = [
        "id",
        Field(
            name="code",
            label="Course Code",
            display=displays.TextDisplay(),
            input_=inputs.TextInput(),
            searchable=True,
        ),
        Field(
            name="name",
            label="Course Name",
            display=displays.TextDisplay(),
            input_=inputs.TextInput(),
            searchable=True,
        ),
        Field(
            name="state",
            label="State",
            display=displays.EnumDisplay(),
            input_=inputs.EnumSelect(),
            searchable=True,
        ),
        Field(
            name="visibility",
            label="Visibility",
            display=displays.EnumDisplay(),
            input_=inputs.EnumSelect(),
            searchable=True,
        ),
        Field(
            name="start_date",
            label="Start Date",
            display=displays.DateDisplay(),
            input_=inputs.DateInput(),
        ),
        Field(
            name="end_date",
            label="End Date",
            display=displays.DateDisplay(),
            input_=inputs.DateInput(),
        ),
        Field(
            name="allow_self_enrollment",
            label="Self Enrollment",
            display=displays.BooleanDisplay(),
            input_=inputs.BooleanInput(),
        ),
        "created_at",
        "updated_at",
    ]


# Section resource
class SectionResource(BaseResource):
    label = "Sections"
    model = Section
    page_pre_title = "sections"
    page_title = "Section Management"
    filters = [
        "name",
        "course__name",
    ]
    fields = [
        "id",
        Field(
            name="name",
            label="Section Name",
            display=displays.TextDisplay(),
            input_=inputs.TextInput(),
            searchable=True,
        ),
        Field(
            name="course",
            label="Course",
            display=displays.ForeignKeyDisplay(display_field="name"),
            input_=inputs.ForeignKeySelect(),
            searchable=True,
        ),
        Field(
            name="max_seats",
            label="Max Seats",
            display=displays.NumberDisplay(),
            input_=inputs.NumberInput(),
        ),
        Field(
            name="meeting_times",
            label="Meeting Times",
            display=displays.TextDisplay(),
            input_=inputs.TextInput(),
        ),
        Field(
            name="location",
            label="Location",
            display=displays.TextDisplay(),
            input_=inputs.TextInput(),
        ),
        "created_at",
        "updated_at",
    ]


# Enrollment resource
class EnrollmentResource(BaseResource):
    label = "Enrollments"
    model = Enrollment
    page_pre_title = "enrollments"
    page_title = "Enrollment Management"
    filters = [
        "user__username",
        "course__name",
        "type",
        "state",
    ]
    fields = [
        "id",
        Field(
            name="user",
            label="User",
            display=displays.ForeignKeyDisplay(display_field="username"),
            input_=inputs.ForeignKeySelect(),
            searchable=True,
        ),
        Field(
            name="course",
            label="Course",
            display=displays.ForeignKeyDisplay(display_field="name"),
            input_=inputs.ForeignKeySelect(),
            searchable=True,
        ),
        Field(
            name="section",
            label="Section",
            display=displays.ForeignKeyDisplay(display_field="name"),
            input_=inputs.ForeignKeySelect(),
            searchable=True,
        ),
        Field(
            name="type",
            label="Type",
            display=displays.EnumDisplay(),
            input_=inputs.EnumSelect(),
            searchable=True,
        ),
        Field(
            name="state",
            label="State",
            display=displays.EnumDisplay(),
            input_=inputs.EnumSelect(),
            searchable=True,
        ),
        Field(
            name="current_grade",
            label="Current Grade",
            display=displays.NumberDisplay(),
            input_=inputs.NumberInput(),
        ),
        Field(
            name="final_grade",
            label="Final Grade",
            display=displays.NumberDisplay(),
            input_=inputs.NumberInput(),
        ),
        "created_at",
        "updated_at",
    ]


# Assignment resource
class AssignmentResource(BaseResource):
    label = "Assignments"
    model = Assignment
    page_pre_title = "assignments"
    page_title = "Assignment Management"
    filters = [
        "title",
        "course__name",
        "assignment_type",
        "published",
    ]
    fields = [
        "id",
        Field(
            name="title",
            label="Title",
            display=displays.TextDisplay(),
            input_=inputs.TextInput(),
            searchable=True,
        ),
        Field(
            name="course",
            label="Course",
            display=displays.ForeignKeyDisplay(display_field="name"),
            input_=inputs.ForeignKeySelect(),
            searchable=True,
        ),
        Field(
            name="assignment_type",
            label="Type",
            display=displays.EnumDisplay(),
            input_=inputs.EnumSelect(),
            searchable=True,
        ),
        Field(
            name="grading_type",
            label="Grading Type",
            display=displays.EnumDisplay(),
            input_=inputs.EnumSelect(),
        ),
        Field(
            name="points_possible",
            label="Points Possible",
            display=displays.NumberDisplay(),
            input_=inputs.NumberInput(),
        ),
        Field(
            name="due_date",
            label="Due Date",
            display=displays.DatetimeDisplay(),
            input_=inputs.DatetimeInput(),
        ),
        Field(
            name="published",
            label="Published",
            display=displays.BooleanDisplay(),
            input_=inputs.BooleanInput(),
            searchable=True,
        ),
        "created_at",
        "updated_at",
    ]


# Module resource
class ModuleResource(BaseResource):
    label = "Modules"
    model = Module
    page_pre_title = "modules"
    page_title = "Module Management"
    filters = [
        "title",
        "course__name",
        "is_published",
    ]
    fields = [
        "id",
        Field(
            name="title",
            label="Title",
            display=displays.TextDisplay(),
            input_=inputs.TextInput(),
            searchable=True,
        ),
        Field(
            name="course",
            label="Course",
            display=displays.ForeignKeyDisplay(display_field="name"),
            input_=inputs.ForeignKeySelect(),
            searchable=True,
        ),
        Field(
            name="position",
            label="Position",
            display=displays.NumberDisplay(),
            input_=inputs.NumberInput(),
        ),
        Field(
            name="is_published",
            label="Published",
            display=displays.BooleanDisplay(),
            input_=inputs.BooleanInput(),
            searchable=True,
        ),
        Field(
            name="is_hidden",
            label="Hidden",
            display=displays.BooleanDisplay(),
            input_=inputs.BooleanInput(),
        ),
        "created_at",
        "updated_at",
    ]


# Quiz resource
class QuizResource(BaseResource):
    label = "Quizzes"
    model = Quiz
    page_pre_title = "quizzes"
    page_title = "Quiz Management"
    filters = [
        "title",
        "course__name",
        "is_published",
    ]
    fields = [
        "id",
        Field(
            name="title",
            label="Title",
            display=displays.TextDisplay(),
            input_=inputs.TextInput(),
            searchable=True,
        ),
        Field(
            name="course",
            label="Course",
            display=displays.ForeignKeyDisplay(display_field="name"),
            input_=inputs.ForeignKeySelect(),
            searchable=True,
        ),
        Field(
            name="assignment",
            label="Assignment",
            display=displays.ForeignKeyDisplay(display_field="title"),
            input_=inputs.ForeignKeySelect(),
        ),
        Field(
            name="quiz_type",
            label="Type",
            display=displays.EnumDisplay(),
            input_=inputs.EnumSelect(),
        ),
        Field(
            name="is_published",
            label="Published",
            display=displays.BooleanDisplay(),
            input_=inputs.BooleanInput(),
            searchable=True,
        ),
        Field(
            name="allowed_attempts",
            label="Allowed Attempts",
            display=displays.NumberDisplay(),
            input_=inputs.NumberInput(),
        ),
        Field(
            name="time_limit_minutes",
            label="Time Limit (minutes)",
            display=displays.NumberDisplay(),
            input_=inputs.NumberInput(),
        ),
        "created_at",
        "updated_at",
    ]


# Resources for Admin site
resources = [
    UserResource,
    CourseResource,
    SectionResource,
    EnrollmentResource,
    AssignmentResource,
    ModuleResource,
    QuizResource,
]

# Navigation links
navigation = [
    Link(
        label="Dashboard",
        url="/admin/dashboard",
        icon="fas fa-home",
    ),
    Link(
        label="User Management",
        url="/admin/users",
        icon="fas fa-users",
        children=[
            UserResource,
        ],
    ),
    Link(
        label="Course Management",
        url="/admin/courses",
        icon="fas fa-book",
        children=[
            CourseResource,
            SectionResource,
            EnrollmentResource,
        ],
    ),
    Link(
        label="Content Management",
        url="/admin/content",
        icon="fas fa-file-alt",
        children=[
            ModuleResource,
            AssignmentResource,
            QuizResource,
        ],
    ),
    Link(
        label="System",
        url="/admin/system",
        icon="fas fa-cogs",
        children=[
            Link(
                label="Site Settings",
                url="/admin/settings",
                icon="fas fa-wrench",
            ),
            Link(
                label="Logs",
                url="/admin/logs",
                icon="fas fa-list",
            ),
        ],
    ),
]