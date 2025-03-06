from enum import Enum
from tortoise import fields, models
from tortoise.contrib.pydantic import pydantic_model_creator


class QuizType(str, Enum):
    PRACTICE = "practice"  # Not graded, for practice only
    GRADED = "graded"  # Counts toward grade
    SURVEY = "survey"  # Collects information, no right/wrong answers
    DIAGNOSTIC = "diagnostic"  # Assesses knowledge/skills


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "multiple_choice"  # Single correct answer
    MULTIPLE_ANSWER = "multiple_answer"  # Multiple correct answers
    TRUE_FALSE = "true_false"  # True/False question
    MATCHING = "matching"  # Match items from two columns
    ESSAY = "essay"  # Free-form written response
    FILL_IN_BLANK = "fill_in_blank"  # Fill in missing words
    NUMERICAL = "numerical"  # Numerical answer
    FORMULA = "formula"  # Mathematical formula
    FILE_UPLOAD = "file_upload"  # Upload file as answer
    SHORT_ANSWER = "short_answer"  # Short text answer
    ORDERING = "ordering"  # Put items in correct order


class Quiz(models.Model):
    """
    Quiz model for assessments and surveys
    """
    
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    
    # Relationships
    course = fields.ForeignKeyField("models.Course", related_name="quizzes")
    assignment = fields.ForeignKeyField("models.Assignment", related_name="quiz", null=True)
    
    # Quiz settings
    quiz_type = fields.CharEnumField(QuizType, default=QuizType.GRADED)
    time_limit_minutes = fields.IntField(null=True)  # Null means no time limit
    shuffle_questions = fields.BooleanField(default=False)
    shuffle_answers = fields.BooleanField(default=False)
    
    # Attempts
    allowed_attempts = fields.IntField(default=1)  # -1 for unlimited
    scoring_policy = fields.CharField(
        max_length=20, default="highest"
    )  # highest, latest, average
    
    # Availability
    is_published = fields.BooleanField(default=False)
    available_from = fields.DatetimeField(null=True)
    available_until = fields.DatetimeField(null=True)
    
    # Question management
    question_count = fields.IntField(default=0)
    points_possible = fields.FloatField(default=0.0)
    
    # Quiz behavior
    show_correct_answers = fields.BooleanField(default=True)
    show_correct_answers_at = fields.DatetimeField(null=True)
    hide_correct_answers_at = fields.DatetimeField(null=True)
    one_question_at_a_time = fields.BooleanField(default=False)
    cant_go_back = fields.BooleanField(default=False)  # Can't navigate back to previous questions
    require_lockdown_browser = fields.BooleanField(default=False)
    
    # Access code for restricted quizzes
    access_code = fields.CharField(max_length=50, null=True)
    
    # IP restrictions
    ip_filter = fields.CharField(max_length=255, null=True)  # Comma-separated list of allowed IPs
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    # Relationships - will be referenced by other models
    # questions: ReverseRelation[QuizQuestion]
    # attempts: ReverseRelation[QuizAttempt]
    
    class Meta:
        table = "quizzes"
    
    def __str__(self):
        return f"{self.title} ({self.course.name})"


class QuestionBank(models.Model):
    """
    Question bank for organizing and reusing questions
    """
    
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    
    # Relationships
    course = fields.ForeignKeyField("models.Course", related_name="question_banks", null=True)
    
    # If this is a global question bank
    is_global = fields.BooleanField(default=False)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    # Relationships - will be referenced by other models
    # questions: ReverseRelation[Question]
    
    class Meta:
        table = "question_banks"
    
    def __str__(self):
        return self.title


class Question(models.Model):
    """
    Question model for quiz questions
    """
    
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255, null=True)  # Optional title/name
    text = fields.TextField()  # Question text
    
    # Question settings
    question_type = fields.CharEnumField(QuestionType, default=QuestionType.MULTIPLE_CHOICE)
    points = fields.FloatField(default=1.0)
    
    # For numerical questions
    numerical_answer = fields.FloatField(null=True)
    numerical_tolerance = fields.FloatField(null=True)
    
    # For formula questions
    formula = fields.TextField(null=True)
    formula_tolerance = fields.FloatField(null=True)
    
    # For fill in blank questions
    fill_in_blank_text = fields.TextField(null=True)  # Text with [blank] placeholders
    
    # Additional settings
    is_partial_credit = fields.BooleanField(default=False)
    feedback = fields.TextField(null=True)  # General feedback
    
    # For ordering questions
    correct_order = fields.JSONField(null=True)  # List of item IDs in correct order
    
    # For matching questions
    matching_pairs = fields.JSONField(null=True)  # List of {left: "...", right: "..."} pairs
    
    # Relationships
    question_bank = fields.ForeignKeyField(
        "models.QuestionBank", related_name="questions", null=True
    )
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    # Relationships - will be referenced by other models
    # answers: ReverseRelation[QuestionAnswer]
    # quiz_questions: ReverseRelation[QuizQuestion]
    
    class Meta:
        table = "questions"
    
    def __str__(self):
        return self.title if self.title else self.text[:50]


class QuestionAnswer(models.Model):
    """
    Answer choices for multiple choice/answer questions
    """
    
    id = fields.IntField(pk=True)
    text = fields.TextField()
    
    # Relationships
    question = fields.ForeignKeyField("models.Question", related_name="answers")
    
    # Answer settings
    is_correct = fields.BooleanField(default=False)
    weight = fields.FloatField(default=100.0)  # Percentage of question points (for partial credit)
    feedback = fields.TextField(null=True)  # Feedback specific to this answer
    
    # For matching questions
    match_id = fields.CharField(max_length=50, null=True)
    
    # For ordering questions
    order_position = fields.IntField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "question_answers"
    
    def __str__(self):
        return f"Answer to {self.question}"


class QuizQuestion(models.Model):
    """
    Links questions to quizzes with position and points
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    quiz = fields.ForeignKeyField("models.Quiz", related_name="questions")
    question = fields.ForeignKeyField("models.Question", related_name="quiz_questions")
    
    # Question settings in this quiz
    position = fields.IntField(default=0)
    points = fields.FloatField(null=True)  # Override the question's default points
    
    # For question groups
    question_group = fields.ForeignKeyField(
        "models.QuizQuestionGroup", related_name="questions", null=True
    )
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "quiz_questions"
        ordering = ["position", "id"]
        unique_together = (("quiz", "question"),)
    
    def __str__(self):
        return f"Question in {self.quiz.title}"


class QuizQuestionGroup(models.Model):
    """
    Group of questions in a quiz, for random selection
    """
    
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255, null=True)
    
    # Relationships
    quiz = fields.ForeignKeyField("models.Quiz", related_name="question_groups")
    
    # Group settings
    position = fields.IntField(default=0)
    pick_count = fields.IntField(default=1)  # Number of questions to pick from group
    points_per_question = fields.FloatField(null=True)  # Override points for all questions
    
    # For question bank picks
    question_bank = fields.ForeignKeyField(
        "models.QuestionBank", related_name="quiz_groups", null=True
    )
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "quiz_question_groups"
        ordering = ["position", "id"]
    
    def __str__(self):
        return f"Question group in {self.quiz.title}"


class QuizAttempt(models.Model):
    """
    Record of a student's attempt at a quiz
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    quiz = fields.ForeignKeyField("models.Quiz", related_name="attempts")
    user = fields.ForeignKeyField("models.User", related_name="quiz_attempts")
    
    # Attempt metadata
    attempt_number = fields.IntField(default=1)
    score = fields.FloatField(null=True)
    
    # Time tracking
    started_at = fields.DatetimeField(auto_now_add=True)
    submitted_at = fields.DatetimeField(null=True)
    time_spent_seconds = fields.IntField(null=True)
    
    # Status
    is_completed = fields.BooleanField(default=False)
    is_graded = fields.BooleanField(default=False)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    # Relationships - will be referenced by other models
    # responses: ReverseRelation[QuizResponse]
    
    class Meta:
        table = "quiz_attempts"
        unique_together = (("quiz", "user", "attempt_number"),)
    
    def __str__(self):
        return f"Attempt #{self.attempt_number} by {self.user.username} on {self.quiz.title}"


class QuizResponse(models.Model):
    """
    Student's response to a quiz question
    """
    
    id = fields.IntField(pk=True)
    
    # Relationships
    attempt = fields.ForeignKeyField("models.QuizAttempt", related_name="responses")
    question = fields.ForeignKeyField("models.Question", related_name="responses")
    
    # Response content depends on question type
    selected_answers = fields.ManyToManyField(
        "models.QuestionAnswer", related_name="quiz_responses"
    )
    text_response = fields.TextField(null=True)  # For essay, short answer
    numerical_response = fields.FloatField(null=True)  # For numerical questions
    file_response = fields.ForeignKeyField(
        "models.File", related_name="quiz_responses", null=True
    )  # For file upload
    
    # For matching questions
    matching_response = fields.JSONField(null=True)  # {left_id: right_id, ...}
    
    # For ordering questions
    ordering_response = fields.JSONField(null=True)  # Array of IDs in student's order
    
    # Grading
    score = fields.FloatField(null=True)
    feedback = fields.TextField(null=True)
    is_correct = fields.BooleanField(null=True)
    
    # For manual grading
    graded_by = fields.ForeignKeyField(
        "models.User", related_name="graded_responses", null=True
    )
    graded_at = fields.DatetimeField(null=True)
    
    # Timestamps
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    
    class Meta:
        table = "quiz_responses"
        unique_together = (("attempt", "question"),)
    
    def __str__(self):
        return f"Response to question in {self.attempt}"


# Pydantic models for validation and serialization
Quiz_Pydantic = pydantic_model_creator(Quiz, name="Quiz")
QuizCreate_Pydantic = pydantic_model_creator(
    Quiz, name="QuizCreate", exclude=("id", "created_at", "updated_at", "question_count", "points_possible")
)

Question_Pydantic = pydantic_model_creator(Question, name="Question")
QuizAttempt_Pydantic = pydantic_model_creator(QuizAttempt, name="QuizAttempt")
QuizResponse_Pydantic = pydantic_model_creator(QuizResponse, name="QuizResponse")