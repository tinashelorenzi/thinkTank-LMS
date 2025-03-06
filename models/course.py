from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class CourseVisibility(str, Enum):
    PUBLIC = "public"          # Anyone can find and access the course
    INSTITUTION = "institution"  # Only people in the same institution can access
    COURSE = "course"          # Only enrolled students can access
    PRIVATE = "private"        # Completely hidden


class CourseState(str, Enum):
    UNPUBLISHED = "unpublished"
    PUBLISHED = "published"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class GradingScheme(str, Enum):
    PERCENTAGE = "percentage"
    LETTER_GRADE = "letter_grade"
    PASS_FAIL = "pass_fail"
    POINTS = "points"


class Course(models.Model):
    """Course model representing a class or course in the LMS"""
    
    id = fields.IntField(pk=True)
    code = fields.CharField(max_length=20, null=True)  # e.g., CS101
    name = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    
    # Course settings
    visibility = fields.CharEnumField(CourseVisibility, default=CourseVisibility.COURSE)
    state = fields.CharEnumField(CourseState, default=CourseState.UNPUBLISHED)
    start_date = fields.DateField(null=True)
    end_date = fields.DateField(null=True)
    
    # Grading
    grading_scheme = fields.CharEnumField(GradingScheme, default=GradingScheme.PERCENTAGE)
    allow_self_enrollment = fields.BooleanField(default=False)
    
    # Syllabus
    syllabus = fields.TextField(null=True)
    
    # Cover image for the course
    image = fields.CharField(max_length=255, null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    # Relationships - will be referenced by other models
    # enrollments: ReverseRelation[Enrollment]
    # assignments: ReverseRelation[Assignment]
    # modules: ReverseRelation[Module]
    # announcements: ReverseRelation[Announcement]
    
    class Meta:
        table = "courses"
    
    def __str__(self):
        return f"{self.code}: {self.name}" if self.code else self.name


class Section(models.Model):
    """Section model representing different sections of a course"""
    
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=100)
    
    # Section specific details
    max_seats = fields.IntField(default=50)
    meeting_times = fields.TextField(null=True)  # Could be JSON field for more complex data
    location = fields.CharField(max_length=100, null=True)
    
    # Relationships
    course = fields.ForeignKeyField("models.Course", related_name="sections")
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "sections"
    
    def __str__(self):
        return f"{self.course.code} - {self.name}" if self.course.code else f"{self.course.name} - {self.name}"


# Pydantic models for validation and serialization
Course_Pydantic = pydantic_model_creator(Course, name="Course")
CourseCreate_Pydantic = pydantic_model_creator(
    Course, name="CourseCreate", exclude=("id", "created_at", "updated_at")
)

Section_Pydantic = pydantic_model_creator(Section, name="Section")
SectionCreate_Pydantic = pydantic_model_creator(
    Section, name="SectionCreate", exclude=("id", "created_at", "updated_at")
)