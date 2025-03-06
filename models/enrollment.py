from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class EnrollmentType(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    TEACHING_ASSISTANT = "teaching_assistant"
    DESIGNER = "designer"
    OBSERVER = "observer"


class EnrollmentState(str, Enum):
    ACTIVE = "active"
    INVITED = "invited"
    PENDING = "pending"
    INACTIVE = "inactive"
    REJECTED = "rejected"
    COMPLETED = "completed"


class Enrollment(models.Model):
    """
    Enrollment model representing the relationship between users and courses.
    This is essentially a join table with additional properties.
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    user = fields.ForeignKeyField("models.User", related_name="enrollments")
    course = fields.ForeignKeyField("models.Course", related_name="enrollments")
    section = fields.ForeignKeyField("models.Section", related_name="enrollments", null=True)
    
    # Enrollment properties
    type = fields.CharEnumField(EnrollmentType, default=EnrollmentType.STUDENT)
    state = fields.CharEnumField(EnrollmentState, default=EnrollmentState.ACTIVE)
    
    # Grades tracking
    current_grade = fields.FloatField(null=True)
    final_grade = fields.FloatField(null=True)
    grade_override = fields.BooleanField(default=False)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    last_activity_at = fields.DatetimeField(null=True)
    
    class Meta:
        table = "enrollments"
        # Ensure a user can only be enrolled once in a specific course-section combo
        unique_together = (("user", "course", "section"),)
    
    def __str__(self):
        return f"{self.user.username} in {self.course.name}"


# Pydantic models for validation and serialization
Enrollment_Pydantic = pydantic_model_creator(Enrollment, name="Enrollment")
EnrollmentCreate_Pydantic = pydantic_model_creator(
    Enrollment, name="EnrollmentCreate", exclude=("id", "created_at", "updated_at", "last_activity_at")
)
EnrollmentUpdate_Pydantic = pydantic_model_creator(
    Enrollment, name="EnrollmentUpdate", exclude_readonly=True, optional=True
)