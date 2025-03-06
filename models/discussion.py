from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class DiscussionVisibility(str, Enum):
    EVERYONE = "everyone"
    INSTRUCTORS = "instructors"
    COURSE_SECTION = "course_section"
    GROUP = "group"


class DiscussionType(str, Enum):
    THREADED = "threaded"  # Traditional threaded discussion
    FOCUSED = "focused"  # Single thread with responses
    Q_AND_A = "q_and_a"  # Question and answer format
    DEBATE = "debate"  # Structured debate format


class DiscussionForum(models.Model):
    """
    Discussion forum model representing a container for discussion topics
    """
    
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    
    # Relationships
    course = fields.ForeignKeyField("models.Course", related_name="discussion_forums")
    module = fields.ForeignKeyField("models.Module", related_name="discussion_forums", null=True)
    
    # Settings
    is_pinned = fields.BooleanField(default=False)
    position = fields.IntField(default=0)  # For ordering forums in the UI
    allow_anonymous_posts = fields.BooleanField(default=False)
    require_initial_post = fields.BooleanField(default=False)  # Must post before seeing others' posts
    
    # If this is a graded discussion
    assignment = fields.ForeignKeyField("models.Assignment", related_name="discussion_forum", null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "discussion_forums"
        ordering = ["position", "created_at"]
    
    def __str__(self):
        return f"{self.title} ({self.course.name})"


class DiscussionTopic(models.Model):
    """
    Discussion topic model representing a thread starter in a forum
    """
    
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    message = fields.TextField()
    
    # Relationships
    forum = fields.ForeignKeyField("models.DiscussionForum", related_name="topics")
    author = fields.ForeignKeyField("models.User", related_name="discussion_topics")
    
    # Settings
    type = fields.CharEnumField(DiscussionType, default=DiscussionType.THREADED)
    visibility = fields.CharEnumField(DiscussionVisibility, default=DiscussionVisibility.EVERYONE)
    is_announcement = fields.BooleanField(default=False)
    is_pinned = fields.BooleanField(default=False)
    allow_liking = fields.BooleanField(default=True)
    is_closed = fields.BooleanField(default=False)  # No more replies allowed
    
    # Statistics
    view_count = fields.IntField(default=0)
    
    # If this topic is only visible to specific users or groups
    visible_to_users = fields.ManyToManyField("models.User", related_name="visible_topics")
    visible_to_groups = fields.ManyToManyField("models.Group", related_name="visible_topics")
    
    # For section-specific topics
    section = fields.ForeignKeyField("models.Section", related_name="discussion_topics", null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "discussion_topics"
    
    def __str__(self):
        return f"{self.title} by {self.author.username}"


class DiscussionReply(models.Model):
    """
    Reply to a discussion topic or another reply
    """
    
    id = fields.IntField(pk=True)
    message = fields.TextField()
    
    # Relationships
    topic = fields.ForeignKeyField("models.DiscussionTopic", related_name="replies")
    author = fields.ForeignKeyField("models.User", related_name="discussion_replies")
    
    # If this is a reply to another reply (for threaded discussions)
    parent_reply = fields.ForeignKeyField(
        "models.DiscussionReply", related_name="child_replies", null=True
    )
    
    # For tracking edits
    is_edited = fields.BooleanField(default=False)
    edited_at = fields.DatetimeField(null=True)
    
    # For instructor endorsement (especially in Q&A discussions)
    is_endorsed = fields.BooleanField(default=False)
    endorsed_by = fields.ForeignKeyField(
        "models.User", related_name="endorsed_replies", null=True
    )
    endorsed_at = fields.DatetimeField(null=True)
    
    # For statistics and sorting
    like_count = fields.IntField(default=0)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "discussion_replies"
    
    def __str__(self):
        return f"Reply by {self.author.username} on {self.topic.title}"


class DiscussionReplyLike(models.Model):
    """
    Likes on discussion replies
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    reply = fields.ForeignKeyField("models.DiscussionReply", related_name="likes")
    user = fields.ForeignKeyField("models.User", related_name="liked_replies")
    
    # Timestamp
    created_at = fields.DatetimeField(auto_now_add=True)
    
    class Meta:
        table = "discussion_reply_likes"
        unique_together = (("reply", "user"),)
    
    def __str__(self):
        return f"Like by {self.user.username} on reply {self.reply.id}"


class DiscussionTopicSubscription(models.Model):
    """
    User subscriptions to discussion topics for notifications
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    topic = fields.ForeignKeyField("models.DiscussionTopic", related_name="subscriptions")
    user = fields.ForeignKeyField("models.User", related_name="topic_subscriptions")
    
    # Subscription settings
    send_email = fields.BooleanField(default=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "discussion_topic_subscriptions"
        unique_together = (("topic", "user"),)
    
    def __str__(self):
        return f"Subscription by {self.user.username} to {self.topic.title}"


# Pydantic models for validation and serialization
DiscussionForum_Pydantic = pydantic_model_creator(DiscussionForum, name="DiscussionForum")
DiscussionForumCreate_Pydantic = pydantic_model_creator(
    DiscussionForum, name="DiscussionForumCreate", exclude=("id", "created_at", "updated_at")
)

DiscussionTopic_Pydantic = pydantic_model_creator(DiscussionTopic, name="DiscussionTopic")
DiscussionTopicCreate_Pydantic = pydantic_model_creator(
    DiscussionTopic, name="DiscussionTopicCreate", exclude=("id", "created_at", "updated_at", "view_count")
)

DiscussionReply_Pydantic = pydantic_model_creator(DiscussionReply, name="DiscussionReply")
DiscussionReplyCreate_Pydantic = pydantic_model_creator(
    DiscussionReply, name="DiscussionReplyCreate", exclude=(
        "id", "created_at", "updated_at", "is_edited", "edited_at", 
        "is_endorsed", "endorsed_by", "endorsed_at", "like_count"
    )
)