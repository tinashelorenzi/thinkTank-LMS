from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field
from datetime import datetime

from models.quiz import QuizType, QuestionType


class QuestionAnswerBase(BaseModel):
    """Base schema for question answer"""
    text: str
    is_correct: bool = False
    weight: float = 100.0
    feedback: Optional[str] = None
    match_id: Optional[str] = None
    order_position: Optional[int] = None


class QuestionAnswerCreate(QuestionAnswerBase):
    """Schema for creating a question answer"""
    pass


class QuestionAnswerResponse(QuestionAnswerBase):
    """Response schema for a question answer"""
    id: int
    
    class Config:
        orm_mode = True


class QuestionBase(BaseModel):
    """Base schema for question"""
    title: Optional[str] = None
    text: str
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE
    points: float = 1.0
    numerical_answer: Optional[float] = None
    numerical_tolerance: Optional[float] = None
    formula: Optional[str] = None
    formula_tolerance: Optional[float] = None
    fill_in_blank_text: Optional[str] = None
    is_partial_credit: bool = False
    feedback: Optional[str] = None
    correct_order: Optional[List[str]] = None
    matching_pairs: Optional[List[Dict[str, str]]] = None
    question_bank_id: Optional[int] = None


class QuestionCreate(QuestionBase):
    """Schema for creating a question"""
    answers: Optional[List[QuestionAnswerCreate]] = []


class QuestionUpdate(BaseModel):
    """Schema for updating a question"""
    title: Optional[str] = None
    text: Optional[str] = None
    question_type: Optional[QuestionType] = None
    points: Optional[float] = None
    numerical_answer: Optional[float] = None
    numerical_tolerance: Optional[float] = None
    formula: Optional[str] = None
    formula_tolerance: Optional[float] = None
    fill_in_blank_text: Optional[str] = None
    is_partial_credit: Optional[bool] = None
    feedback: Optional[str] = None
    correct_order: Optional[List[str]] = None
    matching_pairs: Optional[List[Dict[str, str]]] = None
    question_bank_id: Optional[int] = None


class QuestionResponse(QuestionBase):
    """Response schema for a question"""
    id: int
    answers: List[QuestionAnswerResponse] = []
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class QuizQuestionBase(BaseModel):
    """Base schema for quiz question"""
    quiz_id: int
    question_id: int
    position: int = 0
    points: Optional[float] = None
    question_group_id: Optional[int] = None


class QuizQuestionCreate(QuizQuestionBase):
    """Schema for creating a quiz question"""
    pass


class QuizQuestionResponse(QuizQuestionBase):
    """Response schema for a quiz question"""
    id: int
    question: QuestionResponse
    
    class Config:
        orm_mode = True


class QuizQuestionGroupBase(BaseModel):
    """Base schema for quiz question group"""
    quiz_id: int
    title: Optional[str] = None
    position: int = 0
    pick_count: int = 1
    points_per_question: Optional[float] = None
    question_bank_id: Optional[int] = None


class QuizQuestionGroupCreate(QuizQuestionGroupBase):
    """Schema for creating a quiz question group"""
    pass


class QuizQuestionGroupResponse(QuizQuestionGroupBase):
    """Response schema for a quiz question group"""
    id: int
    questions: List[QuizQuestionResponse] = []
    
    class Config:
        orm_mode = True


class QuizBase(BaseModel):
    """Base schema for quiz"""
    title: str
    description: Optional[str] = None
    course_id: int
    assignment_id: Optional[int] = None
    quiz_type: QuizType = QuizType.GRADED
    time_limit_minutes: Optional[int] = None
    shuffle_questions: bool = False
    shuffle_answers: bool = False
    allowed_attempts: int = 1
    scoring_policy: str = "highest"
    is_published: bool = False
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    show_correct_answers: bool = True
    show_correct_answers_at: Optional[datetime] = None
    hide_correct_answers_at: Optional[datetime] = None
    one_question_at_a_time: bool = False
    cant_go_back: bool = False
    require_lockdown_browser: bool = False
    access_code: Optional[str] = None
    ip_filter: Optional[str] = None


class QuizCreate(QuizBase):
    """Schema for creating a quiz"""
    questions: Optional[List[int]] = []  # IDs of existing questions to add
    new_questions: Optional[List[QuestionCreate]] = []  # New questions to create


class QuizUpdate(BaseModel):
    """Schema for updating a quiz"""
    title: Optional[str] = None
    description: Optional[str] = None
    quiz_type: Optional[QuizType] = None
    time_limit_minutes: Optional[int] = None
    shuffle_questions: Optional[bool] = None
    shuffle_answers: Optional[bool] = None
    allowed_attempts: Optional[int] = None
    scoring_policy: Optional[str] = None
    is_published: Optional[bool] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    show_correct_answers: Optional[bool] = None
    show_correct_answers_at: Optional[datetime] = None
    hide_correct_answers_at: Optional[datetime] = None
    one_question_at_a_time: Optional[bool] = None
    cant_go_back: Optional[bool] = None
    require_lockdown_browser: Optional[bool] = None
    access_code: Optional[str] = None
    ip_filter: Optional[str] = None


class QuizResponse(QuizBase):
    """Response schema for a quiz"""
    id: int
    question_count: int = 0
    points_possible: float = 0.0
    created_at: datetime
    updated_at: datetime
    questions: List[QuizQuestionResponse] = []
    question_groups: List[QuizQuestionGroupResponse] = []
    
    class Config:
        orm_mode = True


class QuizListResponse(BaseModel):
    """Response schema for list of quizzes"""
    total: int
    quizzes: List[QuizResponse]

    class Config:
        orm_mode = True


class QuizResponseBase(BaseModel):
    """Base schema for quiz response"""
    attempt_id: int
    question_id: int
    selected_answers: Optional[List[int]] = None
    text_response: Optional[str] = None
    numerical_response: Optional[float] = None
    file_response_id: Optional[int] = None
    matching_response: Optional[Dict[str, str]] = None
    ordering_response: Optional[List[str]] = None


class QuizResponseCreate(QuizResponseBase):
    """Schema for creating a quiz response"""
    pass


class QuizResponseUpdate(BaseModel):
    """Schema for updating a quiz response"""
    selected_answers: Optional[List[int]] = None
    text_response: Optional[str] = None
    numerical_response: Optional[float] = None
    file_response_id: Optional[int] = None
    matching_response: Optional[Dict[str, str]] = None
    ordering_response: Optional[List[str]] = None


class QuizResponseData(QuizResponseBase):
    """Quiz response with additional data"""
    id: int
    score: Optional[float] = None
    feedback: Optional[str] = None
    is_correct: Optional[bool] = None
    
    class Config:
        orm_mode = True


class QuizAttemptBase(BaseModel):
    """Base schema for quiz attempt"""
    quiz_id: int
    user_id: int
    attempt_number: int = 1


class QuizAttemptCreate(QuizAttemptBase):
    """Schema for creating a quiz attempt"""
    responses: Optional[List[QuizResponseCreate]] = None


class QuizAttemptUpdate(BaseModel):
    """Schema for updating a quiz attempt"""
    score: Optional[float] = None
    is_completed: Optional[bool] = None
    is_graded: Optional[bool] = None
    submitted_at: Optional[datetime] = None
    time_spent_seconds: Optional[int] = None


class QuizAttemptResponse(QuizAttemptBase):
    """Response schema for a quiz attempt"""
    id: int
    score: Optional[float] = None
    started_at: datetime
    submitted_at: Optional[datetime] = None
    time_spent_seconds: Optional[int] = None
    is_completed: bool = False
    is_graded: bool = False
    responses: List[QuizResponseData] = []
    
    class Config:
        orm_mode = True