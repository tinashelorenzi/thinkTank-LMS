from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class SubmissionStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    GRADED = "graded"
    RETURNED = "returned"
    LATE = "late"
    EXCUSED = "excused"
    MISSING = "missing"


class Submission(models.Model):
    """
    Submission model representing student work submitted for an assignment
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    assignment = fields.ForeignKeyField("models.Assignment", related_name="submissions")
    user = fields.ForeignKeyField("models.User", related_name="submissions")
    # If it's a group submission, we track both the submitter and the group
    group = fields.ForeignKeyField("models.Group", related_name="submissions", null=True)
    
    # Submission content - type depends on the submission type in assignment
    submission_type = fields.CharField(max_length=50)  # Matches SubmissionType enum
    body = fields.TextField(null=True)  # For text submissions
    url = fields.CharField(max_length=2048, null=True)  # For URL submissions
    
    # Submission metadata
    status = fields.CharEnumField(SubmissionStatus, default=SubmissionStatus.SUBMITTED)
    attempt_number = fields.IntField(default=1)
    submitted_at = fields.DatetimeField(auto_now_add=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    # Relationships from other models
    # files: ReverseRelation[SubmissionAttachment]
    # grade: ReverseRelation[Grade]
    # comments: ReverseRelation[Comment]
    
    class Meta:
        table = "submissions"
    
    def __str__(self):
        return f"Submission by {self.user.username} for {self.assignment.title}"
    
    @property
    def is_late(self):
        """Check if the submission is late based on the assignment due date"""
        if not self.assignment.due_date:
            return False
        return self.submitted_at > self.assignment.due_date


class SubmissionAttachment(models.Model):
    """
    Files attached to a submission
    """
    
    id = fields.IntField(pk=True)
    submission = fields.ForeignKeyField("models.Submission", related_name="files")
    
    # File information
    filename = fields.CharField(max_length=255)
    file_path = fields.CharField(max_length=1024)  # Storage path
    file_type = fields.CharField(max_length=255)
    file_size = fields.IntField()  # Size in bytes
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "submission_attachments"
    
    def __str__(self):
        return f"{self.filename} ({self.submission.id})"


class Grade(models.Model):
    """
    Grade model for tracking scores on submissions
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    submission = fields.ForeignKeyField("models.Submission", related_name="grades")
    grader = fields.ForeignKeyField("models.User", related_name="grades_given", null=True)
    
    # Grade information
    score = fields.FloatField(null=True)
    feedback = fields.TextField(null=True)
    
    # For tracking if this was automatically graded
    is_auto_graded = fields.BooleanField(default=False)
    
    # If this grade is part of a rubric assessment
    rubric_assessment = fields.JSONField(null=True)
    
    # Timestamps
    graded_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "grades"
    
    def __str__(self):
        return f"Grade for {self.submission}"


class Comment(models.Model):
    """
    Comments on submissions
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    submission = fields.ForeignKeyField("models.Submission", related_name="comments")
    author = fields.ForeignKeyField("models.User", related_name="comments")
    
    # Comment content
    text = fields.TextField()
    
    # For threaded comments
    parent = fields.ForeignKeyField("models.Comment", related_name="replies", null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "comments"
    
    def __str__(self):
        return f"Comment by {self.author.username} on {self.submission}"


# Pydantic models for validation and serialization
Submission_Pydantic = pydantic_model_creator(Submission, name="Submission")
SubmissionCreate_Pydantic = pydantic_model_creator(
    Submission, name="SubmissionCreate", exclude=("id", "created_at", "updated_at")
)

Grade_Pydantic = pydantic_model_creator(Grade, name="Grade")
GradeCreate_Pydantic = pydantic_model_creator(
    Grade, name="GradeCreate", exclude=("id", "created_at", "updated_at", "graded_at")
)

Comment_Pydantic = pydantic_model_creator(Comment, name="Comment")
SubmissionAttachment_Pydantic = pydantic_model_creator(SubmissionAttachment, name="SubmissionAttachment")