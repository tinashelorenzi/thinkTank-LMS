# Export all schemas for easier imports
from .token import Token, TokenPayload
from .user import (
    UserCreate, UserUpdate, UserResponse, 
    UserListResponse, UserInDB, UserUpdatePassword
)
from .course import (
    CourseCreate, CourseUpdate, CourseResponse, 
    CourseListResponse, SectionCreate, SectionUpdate,
    SectionResponse, SectionListResponse
)
from .enrollment import (
    EnrollmentCreate, EnrollmentUpdate, EnrollmentResponse,
    EnrollmentListResponse
)
from .assignment import (
    AssignmentCreate, AssignmentUpdate, AssignmentResponse,
    AssignmentListResponse, RubricResponse
)
from .submission import (
    SubmissionCreate, SubmissionUpdate, SubmissionResponse,
    SubmissionListResponse, GradeResponse
)
from .quiz import (
    QuizCreate, QuizUpdate, QuizResponse, 
    QuestionCreate, QuestionResponse, 
    QuizAttemptResponse
)
from .discussion import (
    DiscussionTopicCreate, DiscussionTopicResponse,
    DiscussionReplyCreate, DiscussionReplyResponse
)