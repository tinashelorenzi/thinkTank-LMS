from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class ModuleType(str, Enum):
    STANDARD = "standard"  # Regular module with content
    HEADER = "header"  # Header-only module for visual organization
    EXTERNAL = "external"  # External tool integration


class CompletionRequirement(str, Enum):
    VIEW = "view"  # Must view the content
    SUBMIT = "submit"  # Must submit the content
    CONTRIBUTE = "contribute"  # Must contribute to the content
    SCORE = "score"  # Must achieve a minimum score
    COMPLETE = "complete"  # Must complete all requirements


class Module(models.Model):
    """
    Module model for organizing course content
    """
    
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    
    # Relationships
    course = fields.ForeignKeyField("models.Course", related_name="modules")
    
    # Module settings
    module_type = fields.CharEnumField(ModuleType, default=ModuleType.STANDARD)
    position = fields.IntField(default=0)  # Order in the course
    
    # Visibility and access
    is_published = fields.BooleanField(default=False)
    is_hidden = fields.BooleanField(default=False)
    available_from = fields.DatetimeField(null=True)
    available_until = fields.DatetimeField(null=True)
    
    # Prerequisites
    prerequisite_modules = fields.ManyToManyField(
        "models.Module", related_name="dependent_modules"
    )
    
    # Completion requirements
    completion_requirement = fields.CharEnumField(
        CompletionRequirement, default=CompletionRequirement.VIEW, null=True
    )
    require_sequential_progress = fields.BooleanField(default=False)
    
    # External tool settings (for LTI tools)
    external_url = fields.CharField(max_length=2048, null=True)
    external_tool_id = fields.CharField(max_length=255, null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    # Relationships - will be referenced by other models
    # items: ReverseRelation[ModuleItem]
    # assignments: ReverseRelation[Assignment]
    # discussion_forums: ReverseRelation[DiscussionForum]
    
    class Meta:
        table = "modules"
        ordering = ["position", "id"]
    
    def __str__(self):
        return f"{self.title} ({self.course.name})"


class ModuleItem(models.Model):
    """
    Individual item within a module
    """
    
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    
    # Relationships
    module = fields.ForeignKeyField("models.Module", related_name="items")
    
    # Item settings
    position = fields.IntField(default=0)  # Order in the module
    
    # Item content type and references
    content_type = fields.CharField(max_length=50)  # e.g., "assignment", "page", "file", "discussion"
    content_id = fields.IntField(null=True)  # ID of the related content
    
    # For direct content
    page_content = fields.TextField(null=True)
    
    # For external content
    external_url = fields.CharField(max_length=2048, null=True)
    
    # For embedded content
    html_content = fields.TextField(null=True)
    
    # For file content
    file = fields.ForeignKeyField("models.File", related_name="module_items", null=True)
    
    # Visibility and access
    is_published = fields.BooleanField(default=True)
    indent_level = fields.IntField(default=0)  # For visual hierarchy
    
    # Completion requirements
    completion_requirement = fields.CharEnumField(
        CompletionRequirement, default=CompletionRequirement.VIEW, null=True
    )
    min_score = fields.FloatField(null=True)  # For score-based completion
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "module_items"
        ordering = ["position", "id"]
    
    def __str__(self):
        return f"{self.title} in {self.module.title}"


class ModuleCompletion(models.Model):
    """
    Tracks user completion of modules
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    module = fields.ForeignKeyField("models.Module", related_name="completions")
    user = fields.ForeignKeyField("models.User", related_name="module_completions")
    
    # Completion status
    is_completed = fields.BooleanField(default=False)
    completed_at = fields.DatetimeField(null=True)
    
    # Progress tracking
    progress_percent = fields.FloatField(default=0.0)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "module_completions"
        unique_together = (("module", "user"),)
    
    def __str__(self):
        return f"Completion for {self.user.username} in {self.module.title}"


class ModuleItemCompletion(models.Model):
    """
    Tracks user completion of module items
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    item = fields.ForeignKeyField("models.ModuleItem", related_name="completions")
    user = fields.ForeignKeyField("models.User", related_name="module_item_completions")
    
    # Completion status
    is_completed = fields.BooleanField(default=False)
    completed_at = fields.DatetimeField(null=True)
    
    # For score-based completion
    score = fields.FloatField(null=True)
    
    # View tracking
    view_count = fields.IntField(default=0)
    last_viewed_at = fields.DatetimeField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "module_item_completions"
        unique_together = (("item", "user"),)
    
    def __str__(self):
        return f"Completion for {self.user.username} in {self.item.title}"


# Pydantic models for validation and serialization
Module_Pydantic = pydantic_model_creator(Module, name="Module")
ModuleCreate_Pydantic = pydantic_model_creator(
    Module, name="ModuleCreate", exclude=("id", "created_at", "updated_at")
)

ModuleItem_Pydantic = pydantic_model_creator(ModuleItem, name="ModuleItem")
ModuleItemCreate_Pydantic = pydantic_model_creator(
    ModuleItem, name="ModuleItemCreate", exclude=("id", "created_at", "updated_at")
)

ModuleCompletion_Pydantic = pydantic_model_creator(ModuleCompletion, name="ModuleCompletion")
ModuleItemCompletion_Pydantic = pydantic_model_creator(ModuleItemCompletion, name="ModuleItemCompletion")