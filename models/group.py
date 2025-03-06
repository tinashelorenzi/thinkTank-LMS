from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class GroupType(str, Enum):
    MANUAL = "manual"  # Manually created group
    SELF_SIGNUP = "self_signup"  # Students can sign up
    RANDOM = "random"  # Randomly assigned
    SET = "set"  # Group set containing multiple groups


class Group(models.Model):
    """
    Group model for student collaboration
    """
    
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    
    # Relationships
    course = fields.ForeignKeyField("models.Course", related_name="groups", null=True)
    group_set = fields.ForeignKeyField("models.GroupSet", related_name="groups", null=True)
    
    # Group settings
    max_members = fields.IntField(null=True)  # Null means no limit
    is_active = fields.BooleanField(default=True)
    
    # For self-signup groups
    join_code = fields.CharField(max_length=20, null=True)
    allow_self_signup = fields.BooleanField(default=False)
    
    # Group leader (if applicable)
    leader = fields.ForeignKeyField("models.User", related_name="led_groups", null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    # Relationships - will be referenced by other models
    # memberships: ReverseRelation[GroupMembership]
    # submissions: ReverseRelation[Submission]
    
    class Meta:
        table = "groups"
    
    def __str__(self):
        course_name = self.course.name if self.course else "No course"
        return f"{self.name} ({course_name})"


class GroupSet(models.Model):
    """
    Set of groups in a course
    """
    
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    
    # Relationships
    course = fields.ForeignKeyField("models.Course", related_name="group_sets")
    
    # Group set settings
    group_type = fields.CharEnumField(GroupType, default=GroupType.MANUAL)
    
    # For self-signup groups
    allow_self_signup = fields.BooleanField(default=False)
    self_signup_deadline = fields.DatetimeField(null=True)
    
    # For random assignment
    create_group_count = fields.IntField(null=True)
    members_per_group = fields.IntField(null=True)
    
    # General settings
    is_active = fields.BooleanField(default=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "group_sets"
        unique_together = (("name", "course"),)
    
    def __str__(self):
        return f"{self.name} ({self.course.name})"


class GroupMembership(models.Model):
    """
    Membership of a user in a group
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    group = fields.ForeignKeyField("models.Group", related_name="memberships")
    user = fields.ForeignKeyField("models.User", related_name="group_memberships")
    
    # Membership settings
    is_active = fields.BooleanField(default=True)
    role = fields.CharField(max_length=50, default="member")  # member, leader, moderator, etc.
    
    # For tracking join/leave
    joined_at = fields.DatetimeField(auto_now_add=True)
    left_at = fields.DatetimeField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "group_memberships"
        unique_together = (("group", "user"),)
    
    def __str__(self):
        return f"{self.user.username} in {self.group.name}"


class GroupAssignment(models.Model):
    """
    Assignment that requires group submission
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    assignment = fields.ForeignKeyField("models.Assignment", related_name="group_assignments")
    group_set = fields.ForeignKeyField("models.GroupSet", related_name="assignments")
    
    # Settings
    require_all_members = fields.BooleanField(default=False)  # Require all members to submit
    grade_individually = fields.BooleanField(default=False)  # Give individual grades
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "group_assignments"
        unique_together = (("assignment", "group_set"),)
    
    def __str__(self):
        return f"{self.assignment.title} ({self.group_set.name})"


class GroupCategory(models.Model):
    """
    Categories for organizing groups
    """
    
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255)
    
    # Relationships
    course = fields.ForeignKeyField("models.Course", related_name="group_categories")
    
    # Settings
    self_signup = fields.BooleanField(default=False)
    auto_leader = fields.BooleanField(default=False)  # Automatically assign first member as leader
    
    # Groups in this category
    groups = fields.ManyToManyField("models.Group", related_name="categories")
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "group_categories"
        unique_together = (("name", "course"),)
    
    def __str__(self):
        return f"{self.name} ({self.course.name})"


class PeerReview(models.Model):
    """
    Peer review assignment within groups
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    assignment = fields.ForeignKeyField("models.Assignment", related_name="peer_reviews")
    reviewer = fields.ForeignKeyField("models.User", related_name="reviews_to_complete")
    reviewee = fields.ForeignKeyField("models.User", related_name="reviews_received")
    
    # If the review is for a specific submission
    submission = fields.ForeignKeyField("models.Submission", related_name="peer_reviews", null=True)
    
    # Review status
    is_completed = fields.BooleanField(default=False)
    completed_at = fields.DatetimeField(null=True)
    
    # Review content
    comments = fields.TextField(null=True)
    rating = fields.FloatField(null=True)
    
    # For rubric-based peer reviews
    rubric_assessment = fields.JSONField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "peer_reviews"
        unique_together = (("assignment", "reviewer", "reviewee"),)
    
    def __str__(self):
        return f"Review by {self.reviewer.username} for {self.reviewee.username}"


class GroupInvitation(models.Model):
    """
    Invitations for users to join groups
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    group = fields.ForeignKeyField("models.Group", related_name="invitations")
    user = fields.ForeignKeyField("models.User", related_name="group_invitations")
    inviter = fields.ForeignKeyField("models.User", related_name="sent_group_invitations")
    
    # Invitation settings
    status = fields.CharField(max_length=20, default="pending")  # pending, accepted, declined, expired
    message = fields.TextField(null=True)
    
    # Expiration
    expires_at = fields.DatetimeField(null=True)
    
    # Response tracking
    responded_at = fields.DatetimeField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "group_invitations"
        unique_together = (("group", "user", "status"),)
    
    def __str__(self):
        return f"Invitation for {self.user.username} to {self.group.name}"


# Pydantic models for validation and serialization
Group_Pydantic = pydantic_model_creator(Group, name="Group")
GroupCreate_Pydantic = pydantic_model_creator(
    Group, name="GroupCreate", exclude=("id", "created_at", "updated_at")
)

GroupSet_Pydantic = pydantic_model_creator(GroupSet, name="GroupSet")
GroupMembership_Pydantic = pydantic_model_creator(GroupMembership, name="GroupMembership")
GroupAssignment_Pydantic = pydantic_model_creator(GroupAssignment, name="GroupAssignment")
PeerReview_Pydantic = pydantic_model_creator(PeerReview, name="PeerReview")