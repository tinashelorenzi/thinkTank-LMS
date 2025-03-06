from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class GradeStatusEnum(str, Enum):
    """Status of a grade in the system"""
    INITIAL = "initial"  # Grade has been created but not finalized
    FINALIZED = "finalized"  # Grade has been finalized and cannot be modified
    OVERRIDDEN = "overridden"  # Grade has been manually overridden
    EXCLUDED = "excluded"  # Grade is excluded from final grade calculation


class GradeSource(str, Enum):
    """Source of the grade"""
    MANUAL = "manual"  # Manually entered by instructor
    AUTOMATIC = "automatic"  # Automatically calculated
    IMPORTED = "imported"  # Imported from external system


class GradeBook(models.Model):
    """
    GradeBook model for tracking overall grades for a course
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    course = fields.ForeignKeyField("models.Course", related_name="gradebooks")
    user = fields.ForeignKeyField("models.User", related_name="gradebooks")
    
    # Overall grade information
    current_score = fields.FloatField(null=True)
    final_score = fields.FloatField(null=True)
    letter_grade = fields.CharField(max_length=10, null=True)
    
    # Additional metadata
    is_passing = fields.BooleanField(default=True)
    notes = fields.TextField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "gradebooks"
        unique_together = (("course", "user"),)
    
    def __str__(self):
        return f"Gradebook for {self.user.username} in {self.course.name}"


class GradeEntry(models.Model):
    """
    Individual grade entry for a particular assignment
    This extends the basic Grade model with more detailed tracking information
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    gradebook = fields.ForeignKeyField("models.GradeBook", related_name="entries")
    assignment = fields.ForeignKeyField("models.Assignment", related_name="grade_entries")
    submission = fields.ForeignKeyField("models.Submission", related_name="grade_entry", null=True)
    grader = fields.ForeignKeyField("models.User", related_name="grades_given", null=True)
    
    # Grade information
    score = fields.FloatField(null=True)
    percentage = fields.FloatField(null=True)  # Calculated percentage based on points possible
    letter_grade = fields.CharField(max_length=10, null=True)
    
    # Metadata
    status = fields.CharEnumField(GradeStatusEnum, default=GradeStatusEnum.INITIAL)
    source = fields.CharEnumField(GradeSource, default=GradeSource.MANUAL)
    feedback = fields.TextField(null=True)
    
    # Late submission calculations
    late_penalty_applied = fields.FloatField(default=0.0)  # Amount deducted for late submission
    original_score = fields.FloatField(null=True)  # Score before any penalties
    
    # Timestamps
    graded_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "grade_entries"
        unique_together = (("gradebook", "assignment"),)
    
    def __str__(self):
        return f"Grade for {self.assignment.title} - {self.gradebook.user.username}"


class GradingSchemeTemplate(models.Model):
    """
    Grading scheme template for defining letter grade boundaries
    """
    
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    
    # The scheme is stored as a JSON object with percentage boundaries
    # e.g. {"A": 90, "B": 80, "C": 70, "D": 60, "F": 0}
    scheme = fields.JSONField()
    
    # If this is a global scheme or specific to a course
    is_global = fields.BooleanField(default=False)
    course = fields.ForeignKeyField("models.Course", related_name="grading_schemes", null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "grading_scheme_templates"
    
    def __str__(self):
        return self.name
    
    def calculate_letter_grade(self, percentage):
        """Calculate the letter grade based on the percentage"""
        if not percentage:
            return None
            
        sorted_boundaries = sorted(
            [(grade, bound) for grade, bound in self.scheme.items()], 
            key=lambda x: x[1], 
            reverse=True
        )
        
        for grade, minimum in sorted_boundaries:
            if percentage >= minimum:
                return grade
                
        return list(self.scheme.keys())[-1]  # Return the lowest grade if no match


class GradingCurve(models.Model):
    """
    Grading curve for adjusting assignment scores
    """
    
    id = fields.IntField(pk=True)
    assignment = fields.ForeignKeyField("models.Assignment", related_name="grading_curves")
    
    # Curve parameters
    curve_type = fields.CharField(max_length=50)  # e.g., "flat", "percentage", "distribution"
    adjustment_value = fields.FloatField()  # The value to adjust by, meaning depends on curve_type
    
    # Additional parameters for complex curves
    parameters = fields.JSONField(null=True)
    
    # Whether the curve has been applied
    is_applied = fields.BooleanField(default=False)
    applied_at = fields.DatetimeField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "grading_curves"
    
    def __str__(self):
        return f"Curve for {self.assignment.title}"


# Pydantic models for validation and serialization
GradeBook_Pydantic = pydantic_model_creator(GradeBook, name="GradeBook")
GradeBookCreate_Pydantic = pydantic_model_creator(
    GradeBook, name="GradeBookCreate", exclude=("id", "created_at", "updated_at")
)

GradeEntry_Pydantic = pydantic_model_creator(GradeEntry, name="GradeEntry")
GradeEntryCreate_Pydantic = pydantic_model_creator(
    GradeEntry, name="GradeEntryCreate", exclude=("id", "created_at", "updated_at", "graded_at")
)

GradingSchemeTemplate_Pydantic = pydantic_model_creator(GradingSchemeTemplate, name="GradingSchemeTemplate")
GradingCurve_Pydantic = pydantic_model_creator(GradingCurve, name="GradingCurve")