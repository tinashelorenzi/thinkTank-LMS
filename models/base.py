from tortoise import fields, models


class TimestampMixin:
    """
    Mixin to add created_at and updated_at fields to models
    """
    
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)


class SoftDeleteMixin:
    """
    Mixin to add soft delete capability to models
    """
    
    is_deleted = fields.BooleanField(default=False)
    deleted_at = fields.DatetimeField(null=True)


class BaseModel(models.Model, TimestampMixin):
    """
    Base model with ID and timestamps for all models to inherit from
    """
    
    id = fields.IntField(pk=True)
    
    class Meta:
        abstract = True


class BaseNamedModel(BaseModel):
    """
    Base model with name and description fields
    """
    
    name = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    
    class Meta:
        abstract = True
    
    def __str__(self):
        return self.name


class BaseSoftDeleteModel(BaseModel, SoftDeleteMixin):
    """
    Base model with soft delete functionality
    """
    
    class Meta:
        abstract = True


class BaseUserOwnedModel(BaseModel):
    """
    Base model for items owned by a user
    """
    
    owner = fields.ForeignKeyField("models.User", related_name="owned_%(class)ss")
    
    class Meta:
        abstract = True


class BaseCourseModel(BaseModel):
    """
    Base model for items associated with a course
    """
    
    course = fields.ForeignKeyField("models.Course", related_name="%(class)ss")
    
    class Meta:
        abstract = True


class BaseUserCourseModel(BaseModel):
    """
    Base model for items associated with both a user and a course
    """
    
    user = fields.ForeignKeyField("models.User", related_name="%(class)ss")
    course = fields.ForeignKeyField("models.Course", related_name="user_%(class)ss")
    
    class Meta:
        abstract = True


class BasePublishableModel(BaseModel):
    """
    Base model for content that can be published or drafted
    """
    
    is_published = fields.BooleanField(default=False)
    published_at = fields.DatetimeField(null=True)
    
    class Meta:
        abstract = True


class BaseOrderedModel(BaseModel):
    """
    Base model for items with a specific order/position
    """
    
    position = fields.IntField(default=0)
    
    class Meta:
        abstract = True
        ordering = ["position", "id"]


class BaseContentModel(BaseNamedModel):
    """
    Base model for content items with publishing status
    """
    
    content = fields.TextField(null=True)
    is_published = fields.BooleanField(default=False)
    published_at = fields.DatetimeField(null=True)
    
    class Meta:
        abstract = True


class BaseCommentModel(BaseModel):
    """
    Base model for comments
    """
    
    author = fields.ForeignKeyField("models.User", related_name="authored_%(class)ss")
    text = fields.TextField()
    is_hidden = fields.BooleanField(default=False)
    
    class Meta:
        abstract = True


class BaseVersionedModel(BaseModel):
    """
    Base model for items with version history
    """
    
    version = fields.IntField(default=1)
    is_latest = fields.BooleanField(default=True)
    
    class Meta:
        abstract = True


class BaseAttachmentModel(BaseModel):
    """
    Base model for attachments
    """
    
    file = fields.ForeignKeyField("models.File", related_name="%(class)s_attachments")
    display_name = fields.CharField(max_length=255, null=True)
    
    class Meta:
        abstract = True


class BaseSettingsModel(BaseModel):
    """
    Base model for settings
    """
    
    settings = fields.JSONField(default=dict)
    
    class Meta:
        abstract = True