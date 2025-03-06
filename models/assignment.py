from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class AssignmentType(str, Enum):
    ASSIGNMENT = "assignment"
    QUIZ = "quiz"
    DISCUSSION = "discussion"
    PROJECT = "project"
    EXAM = "exam"
    OTHER = "other"


class SubmissionType(str, Enum):
    ONLINE_TEXT = "online_text"
    ONLINE_URL = "online_url"
    ONLINE_UPLOAD = "online_upload"
    ONLINE_QUIZ = "online_quiz"
    EXTERNAL_TOOL = "external_tool"
    NO_SUBMISSION = "no_submission"


class GradingType(str, Enum):
    POINTS = "points"
    PERCENTAGE = "percentage"
    LETTER_GRADE = "letter_grade"
    GPA_SCALE = "gpa_scale"
    PASS_FAIL = "pass_fail"
    NOT_GRADED = "not_graded"


class Assignment(models.Model):
    """
    Assignment model representing any gradable activity in a course
    """
    
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    
    # Assignment settings
    assignment_type = fields.CharEnumField(AssignmentType, default=AssignmentType.ASSIGNMENT)
    submission_types = fields.JSONField(default=lambda: [SubmissionType.ONLINE_TEXT])
    
    # Grading
    grading_type = fields.CharEnumField(GradingType, default=GradingType.POINTS)
    points_possible = fields.FloatField(default=100.0)
    grading_scheme = fields.JSONField(null=True)  # For custom grading schemes
    
    # Dates
    due_date = fields.DatetimeField(null=True)
    available_from = fields.DatetimeField(null=True)
    available_until = fields.DatetimeField(null=True)
    
    # Flags
    published = fields.BooleanField(default=False)
    allow_late_submissions = fields.BooleanField(default=True)
    late_penalty_percent = fields.FloatField(default=0.0)  # e.g., 10.0 for 10% penalty
    max_attempts = fields.IntField(default=1)  # -1 for unlimited
    
    # Group settings
    is_group_assignment = fields.BooleanField(default=False)
    
    # Course relationship
    course = fields.ForeignKeyField("models.Course", related_name="assignments")
    module = fields.ForeignKeyField("models.Module", related_name="assignments", null=True)
    
    # For assignments that are part of a weighted assignment group
    assignment_group = fields.ForeignKeyField(
        "models.AssignmentGroup", related_name="assignments", null=True
    )
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    # Relationships to be defined in other models
    # submissions: ReverseRelation[Submission]
    
    class Meta:
        table = "assignments"
    
    def __str__(self):
        return f"{self.title} ({self.course.name})"


class AssignmentGroup(models.Model):
    """
    Assignment group for organizing assignments and weighting grade calculations
    """
    
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    weight = fields.FloatField(default=0.0)  # Percentage weight in course grade
    
    # Course relationship
    course = fields.ForeignKeyField("models.Course", related_name="assignment_groups")
    
    # Drop lowest settings
    drop_lowest = fields.IntField(default=0)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "assignment_groups"
        unique_together = (("name", "course"),)
    
    def __str__(self):
        return f"{self.name} ({self.course.name})"


class Rubric(models.Model):
    """
    Rubric model for structured grading criteria
    """
    
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    
    # Course relationship - optional as rubrics can be reused across courses
    course = fields.ForeignKeyField("models.Course", related_name="rubrics", null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "rubrics"
    
    def __str__(self):
        return self.title


class RubricCriterion(models.Model):
    """
    Individual criterion in a rubric
    """
    
    id = fields.IntField(pk=True)
    rubric = fields.ForeignKeyField("models.Rubric", related_name="criteria")
    description = fields.TextField()
    points = fields.FloatField()
    
    # Ordering in the rubric
    position = fields.IntField(default=0)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "rubric_criteria"
        ordering = ["position"]
    
    def __str__(self):
        return f"{self.description} ({self.points} pts)"


class RubricRating(models.Model):
    """
    Rating levels for a rubric criterion
    """
    
    id = fields.IntField(pk=True)
    criterion = fields.ForeignKeyField("models.RubricCriterion", related_name="ratings")
    description = fields.TextField()
    points = fields.FloatField()
    
    # Ordering within the criterion
    position = fields.IntField(default=0)
    
    class Meta:
        table = "rubric_ratings"
        ordering = ["position"]
    
    def __str__(self):
        return f"{self.description} ({self.points} pts)"


# Pydantic models for validation and serialization
Assignment_Pydantic = pydantic_model_creator(Assignment, name="Assignment")
AssignmentCreate_Pydantic = pydantic_model_creator(
    Assignment, name="AssignmentCreate", exclude=("id", "created_at", "updated_at")
)

AssignmentGroup_Pydantic = pydantic_model_creator(AssignmentGroup, name="AssignmentGroup")
Rubric_Pydantic = pydantic_model_creator(Rubric, name="Rubric", include_related=True)