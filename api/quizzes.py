from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, BackgroundTasks

from models.course import Course
from models.user import User, UserRole
from models.enrollment import Enrollment, EnrollmentType, EnrollmentState
from models.quiz import (
    Quiz, Question, QuestionAnswer, QuizQuestion, QuizQuestionGroup,
    QuizAttempt, QuizResponse, QuestionBank,
    QuizType, QuestionType
)
from models.module import Module
from models.assignment import Assignment
from schemas.quiz import (
    QuizCreate, QuizUpdate, QuizResponse, QuizListResponse,
    QuestionCreate, QuestionUpdate, QuestionResponse,
    QuizAttemptCreate, QuizAttemptUpdate, QuizAttemptResponse,
    QuizResponseCreate, QuizResponseUpdate
)
from core.security import (
    get_current_user,
    get_current_active_user,
    get_current_instructor_or_admin
)
from utils.pagination import get_page_params, paginate_queryset, PageParams
from core.config import settings

# Create quizzes router
router = APIRouter(prefix="/quizzes", tags=["quizzes"])


@router.post("", response_model=QuizResponse, status_code=status.HTTP_201_CREATED)
async def create_quiz(
        quiz_in: QuizCreate,
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create a new quiz (instructor or admin only)
    """
    # Get course
    course = await Course.get_or_none(id=quiz_in.course_id)

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    # Check if user has permission to create quizzes for this course
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()

        if not is_instructor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create quizzes for this course",
            )

    # Check assignment if provided
    assignment = None
    if quiz_in.assignment_id:
        assignment = await Assignment.get_or_none(id=quiz_in.assignment_id, course=course)

        if not assignment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found",
            )

    # Create quiz
    quiz = await Quiz.create(
        title=quiz_in.title,
        description=quiz_in.description,
        course=course,
        assignment=assignment,
        quiz_type=quiz_in.quiz_type,
        time_limit_minutes=quiz_in.time_limit_minutes,
        shuffle_questions=quiz_in.shuffle_questions,
        shuffle_answers=quiz_in.shuffle_answers,
        allowed_attempts=quiz_in.allowed_attempts,
        scoring_policy=quiz_in.scoring_policy,
        is_published=quiz_in.is_published,
        available_from=quiz_in.available_from,
        available_until=quiz_in.available_until,
        show_correct_answers=quiz_in.show_correct_answers,
        show_correct_answers_at=quiz_in.show_correct_answers_at,
        hide_correct_answers_at=quiz_in.hide_correct_answers_at,
        one_question_at_a_time=quiz_in.one_question_at_a_time,
        cant_go_back=quiz_in.cant_go_back,
        require_lockdown_browser=quiz_in.require_lockdown_browser,
        access_code=quiz_in.access_code,
        ip_filter=quiz_in.ip_filter,
    )

    # Process existing questions to add
    if quiz_in.questions:
        position = 0
        for question_id in quiz_in.questions:
            question = await Question.get_or_none(id=question_id)

            if question:
                await QuizQuestion.create(
                    quiz=quiz,
                    question=question,
                    position=position,
                )
                position += 1
                quiz.points_possible += question.points

        quiz.question_count = len(quiz_in.questions)
        await quiz.save()

    # Process new questions to create
    if quiz_in.new_questions:
        position = quiz.question_count

        for question_in in quiz_in.new_questions:
            # Create question
            question = await Question.create(
                title=question_in.title,
                text=question_in.text,
                question_type=question_in.question_type,
                points=question_in.points,
                numerical_answer=question_in.numerical_answer,
                numerical_tolerance=question_in.numerical_tolerance,
                formula=question_in.formula,
                formula_tolerance=question_in.formula_tolerance,
                fill_in_blank_text=question_in.fill_in_blank_text,
                is_partial_credit=question_in.is_partial_credit,
                feedback=question_in.feedback,
                correct_order=question_in.correct_order,
                matching_pairs=question_in.matching_pairs,
                question_bank_id=question_in.question_bank_id,
            )

            # Create answers for the question
            if question_in.answers:
                for answer_in in question_in.answers:
                    await QuestionAnswer.create(
                        text=answer_in.text,
                        question=question,
                        is_correct=answer_in.is_correct,
                        weight=answer_in.weight,
                        feedback=answer_in.feedback,
                        match_id=answer_in.match_id,
                        order_position=answer_in.order_position,
                    )

            # Add question to quiz
            await QuizQuestion.create(
                quiz=quiz,
                question=question,
                position=position,
            )

            position += 1

            # Update points possible
            quiz.points_possible += question.points

        # Update question count
        quiz.question_count += len(quiz_in.new_questions)
        await quiz.save()

    return quiz


@router.get("", response_model=QuizListResponse)
async def list_quizzes(
        page_params: PageParams = Depends(get_page_params),
        course_id: int = Query(..., description="Course ID"),
        include_unpublished: bool = Query(False, description="Include unpublished quizzes"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List quizzes for a course
    """
    # Get course
    course = await Course.get_or_none(id=course_id)

    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found",
        )

    # Check if user can access this course
    if current_user.role != UserRole.ADMIN:
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

    # Create base query
    query = Quiz.filter(course=course)

    # For non-admin/non-instructor users, only show published quizzes
    is_instructor = False
    if current_user.role != UserRole.ADMIN:
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()

        if not is_instructor and not include_unpublished:
            query = query.filter(is_published=True)

    # Get paginated results
    quizzes = await paginate_queryset(
        queryset=query,
        page_params=page_params,
        pydantic_model=QuizResponse,
    )

    # Add question count and points possible to each quiz
    for quiz in quizzes.items:
        quiz_questions = await QuizQuestion.filter(quiz_id=quiz.id).all()
        quiz.question_count = len(quiz_questions)

        # Calculate total points
        total_points = 0
        for quiz_question in quiz_questions:
            question = await Question.get(id=quiz_question.question_id)
            total_points += question.points

        quiz.points_possible = total_points

    return quizzes


@router.get("/{quiz_id}", response_model=QuizResponse)
async def get_quiz(
        quiz_id: int = Path(..., description="The ID of the quiz"),
        include_questions: bool = Query(False, description="Include questions in the response"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get quiz by ID
    """
    # Get quiz
    quiz = await Quiz.get_or_none(id=quiz_id).prefetch_related("course", "assignment")

    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    # Check if user can access this quiz
    if current_user.role != UserRole.ADMIN:
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=quiz.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

        # Check if quiz is published (for non-instructors)
        is_instructor = enrollment.type == EnrollmentType.TEACHER
        if not is_instructor and not quiz.is_published:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This quiz is not published",
            )

        # Check availability dates
        now = datetime.utcnow()
        if not is_instructor:
            if quiz.available_from and now < quiz.available_from:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This quiz is not available yet",
                )

            if quiz.available_until and now > quiz.available_until:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This quiz is no longer available",
                )

    # Get quiz questions and groups
    quiz_questions = []
    question_groups = []

    if include_questions:
        # Get regular quiz questions
        quiz_question_relations = await QuizQuestion.filter(
            quiz=quiz,
            question_group=None
        ).prefetch_related("question").order_by("position").all()

        for quiz_question in quiz_question_relations:
            # Get question answers
            question = quiz_question.question
            answers = await QuestionAnswer.filter(question=question).all()

            # Add answers to question
            question.answers = answers

            # Add to questions list
            quiz_questions.append({
                "id": quiz_question.id,
                "quiz_id": quiz.id,
                "question_id": quiz_question.question.id,
                "position": quiz_question.position,
                "points": quiz_question.points or quiz_question.question.points,
                "question": question,
            })

        # Get question groups
        group_relations = await QuizQuestionGroup.filter(
            quiz=quiz
        ).prefetch_related("questions", "questions__question").order_by("position").all()

        for group in group_relations:
            group_questions = []

            for quiz_question in group.questions:
                question = quiz_question.question
                answers = await QuestionAnswer.filter(question=question).all()

                # Add answers to question
                question.answers = answers

                # Add to group questions
                group_questions.append({
                    "id": quiz_question.id,
                    "quiz_id": quiz.id,
                    "question_id": quiz_question.question.id,
                    "position": quiz_question.position,
                    "points": quiz_question.points or quiz_question.question.points,
                    "question": question,
                })

            question_groups.append({
                "id": group.id,
                "quiz_id": quiz.id,
                "title": group.title,
                "position": group.position,
                "pick_count": group.pick_count,
                "points_per_question": group.points_per_question,
                "question_bank_id": group.question_bank_id,
                "questions": group_questions,
            })

    # Add questions and groups to quiz
    quiz.questions = quiz_questions
    quiz.question_groups = question_groups

    # Calculate question count and points possible
    quiz.question_count = len(quiz_questions)
    for group in question_groups:
        if group["pick_count"] <= len(group["questions"]):
            quiz.question_count += group["pick_count"]
        else:
            quiz.question_count += len(group["questions"])

    # Calculate total points
    total_points = 0
    for quiz_question in quiz_questions:
        total_points += quiz_question["points"]

    for group in question_groups:
        if group["points_per_question"]:
            total_points += group["points_per_question"] * group["pick_count"]
        else:
            # Use average of question points
            group_points = sum(q["points"] for q in group["questions"])
            avg_points = group_points / len(group["questions"]) if group["questions"] else 0
            total_points += avg_points * group["pick_count"]

    quiz.points_possible = total_points

    return quiz


@router.put("/{quiz_id}", response_model=QuizResponse)
async def update_quiz(
        quiz_in: QuizUpdate,
        quiz_id: int = Path(..., description="The ID of the quiz"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Update a quiz (instructor or admin only)
    """
    # Get quiz
    quiz = await Quiz.get_or_none(id=quiz_id).prefetch_related("course")

    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    # Check if user has permission to update this quiz
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=quiz.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()

        if not is_instructor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this quiz",
            )

    # Update fields
    for field, value in quiz_in.dict(exclude_unset=True).items():
        setattr(quiz, field, value)

    # Save quiz
    await quiz.save()

    # Calculate question count and points possible
    quiz_questions = await QuizQuestion.filter(quiz=quiz, question_group=None).all()
    groups = await QuizQuestionGroup.filter(quiz=quiz).all()

    quiz.question_count = len(quiz_questions)
    for group in groups:
        group_questions = await QuizQuestion.filter(question_group=group).count()
        if group.pick_count <= group_questions:
            quiz.question_count += group.pick_count
        else:
            quiz.question_count += group_questions

    # Calculate total points
    total_points = 0
    for quiz_question in quiz_questions:
        question = await Question.get(id=quiz_question.question_id)
        total_points += quiz_question.points or question.points

    for group in groups:
        if group.points_per_question:
            total_points += group.points_per_question * group.pick_count
        else:
            # Use average of question points
            group_question_relations = await QuizQuestion.filter(question_group=group).all()
            group_points = 0
            for quiz_question in group_question_relations:
                question = await Question.get(id=quiz_question.question_id)
                group_points += quiz_question.points or question.points

            avg_points = group_points / len(group_question_relations) if group_question_relations else 0
            total_points += avg_points * group.pick_count

    quiz.points_possible = total_points
    await quiz.save()

    return quiz


@router.delete("/{quiz_id}", response_model=Dict[str, Any])
async def delete_quiz(
        quiz_id: int = Path(..., description="The ID of the quiz"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Delete a quiz (instructor or admin only)
    """
    # Get quiz
    quiz = await Quiz.get_or_none(id=quiz_id).prefetch_related("course")

    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    # Check if user has permission to delete this quiz
    if current_user.role != UserRole.ADMIN:
        # Check if user is instructor of the course
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=quiz.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()

        if not is_instructor:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this quiz",
            )

    # Check if quiz has been attempted
    attempts = await QuizAttempt.filter(quiz=quiz).count()

    if attempts > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete quiz with {attempts} attempts. Archive it instead.",
        )

    # Delete quiz questions and groups
    await QuizQuestion.filter(quiz=quiz).delete()
    await QuizQuestionGroup.filter(quiz=quiz).delete()

    # Delete quiz
    await quiz.delete()

    return {"message": "Quiz deleted successfully"}


@router.post("/questions", response_model=QuestionResponse, status_code=status.HTTP_201_CREATED)
async def create_question(
        question_in: QuestionCreate,
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create a new question (instructor or admin only)
    """
    # Create question
    question = await Question.create(
        title=question_in.title,
        text=question_in.text,
        question_type=question_in.question_type,
        points=question_in.points,
        numerical_answer=question_in.numerical_answer,
        numerical_tolerance=question_in.numerical_tolerance,
        formula=question_in.formula,
        formula_tolerance=question_in.formula_tolerance,
        fill_in_blank_text=question_in.fill_in_blank_text,
        is_partial_credit=question_in.is_partial_credit,
        feedback=question_in.feedback,
        correct_order=question_in.correct_order,
        matching_pairs=question_in.matching_pairs,
        question_bank_id=question_in.question_bank_id,
    )

    # Create answers for the question
    if question_in.answers:
        for answer_in in question_in.answers:
            await QuestionAnswer.create(
                text=answer_in.text,
                question=question,
                is_correct=answer_in.is_correct,
                weight=answer_in.weight,
                feedback=answer_in.feedback,
                match_id=answer_in.match_id,
                order_position=answer_in.order_position,
            )

    # Get all answers for the question
    answers = await QuestionAnswer.filter(question=question).all()
    question.answers = answers

    return question


@router.get("/questions/{question_id}", response_model=QuestionResponse)
async def get_question(
        question_id: int = Path(..., description="The ID of the question"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Get question by ID (instructor or admin only)
    """
    # Get question
    question = await Question.get_or_none(id=question_id)

    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )

    # Get answers for the question
    answers = await QuestionAnswer.filter(question=question).all()
    question.answers = answers

    return question


@router.put("/questions/{question_id}", response_model=QuestionResponse)
async def update_question(
        question_in: QuestionUpdate,
        question_id: int = Path(..., description="The ID of the question"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Update a question (instructor or admin only)
    """
    # Get question
    question = await Question.get_or_none(id=question_id)

    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )

    # Update fields
    for field, value in question_in.dict(exclude_unset=True, exclude={"answers"}).items():
        setattr(question, field, value)

    # Save question
    await question.save()

    # Update answers if provided
    if question_in.answers is not None:
        # Delete existing answers
        await QuestionAnswer.filter(question=question).delete()

        # Create new answers
        for answer_in in question_in.answers:
            await QuestionAnswer.create(
                text=answer_in.text,
                question=question,
                is_correct=answer_in.is_correct,
                weight=answer_in.weight,
                feedback=answer_in.feedback,
                match_id=answer_in.match_id,
                order_position=answer_in.order_position,
            )

    # Get all answers for the question
    answers = await QuestionAnswer.filter(question=question).all()
    question.answers = answers

    return question


@router.post("/{quiz_id}/attempts", response_model=QuizAttemptResponse, status_code=status.HTTP_201_CREATED)
async def start_quiz_attempt(
        quiz_id: int = Path(..., description="The ID of the quiz"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Start a new quiz attempt
    """
    # Get quiz
    quiz = await Quiz.get_or_none(id=quiz_id).prefetch_related("course")

    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    # Check if user can access this quiz
    if current_user.role != UserRole.ADMIN:
        # Check enrollment
        enrollment = await Enrollment.get_or_none(
            user=current_user,
            course=quiz.course,
            state=EnrollmentState.ACTIVE,
        )

        if not enrollment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not enrolled in this course",
            )

        # Check if quiz is published
        if not quiz.is_published:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This quiz is not published",
            )

        # Check availability dates
        now = datetime.utcnow()
        if quiz.available_from and now < quiz.available_from:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This quiz is not available yet",
            )

        if quiz.available_until and now > quiz.available_until:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This quiz is no longer available",
            )

    # Check attempt limit
    if quiz.allowed_attempts > 0:
        attempt_count = await QuizAttempt.filter(quiz=quiz, user=current_user).count()

        if attempt_count >= quiz.allowed_attempts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum number of attempts ({quiz.allowed_attempts}) reached",
            )

    # Get next attempt number
    next_attempt = await QuizAttempt.filter(quiz=quiz, user=current_user).count() + 1

    # Create quiz attempt
    attempt = await QuizAttempt.create(
        quiz=quiz,
        user=current_user,
        attempt_number=next_attempt,
    )

    # Get questions for the attempt
    questions = []

    # Get regular quiz questions
    quiz_questions = await QuizQuestion.filter(
        quiz=quiz,
        question_group=None
    ).prefetch_related("question").order_by("position").all()

    for quiz_question in quiz_questions:
        question = quiz_question.question
        questions.append({
            "id": question.id,
            "quiz_question_id": quiz_question.id,
            "points": quiz_question.points or question.points,
        })

    # Get question groups
    groups = await QuizQuestionGroup.filter(quiz=quiz).prefetch_related("questions", "questions__question").all()

    for group in groups:
        group_questions = []

        # Get all questions in the group
        for quiz_question in await QuizQuestion.filter(question_group=group).prefetch_related("question").all():
            question = quiz_question.question
            group_questions.append({
                "id": question.id,
                "quiz_question_id": quiz_question.id,
                "points": quiz_question.points or question.points,
            })

        # Randomly select questions if pick_count is less than available questions
        import random
        if group.pick_count < len(group_questions):
            group_questions = random.sample(group_questions, group.pick_count)

        # Add selected questions to the list
        questions.extend(group_questions)

    # Shuffle questions if enabled
    if quiz.shuffle_questions:
        import random
        random.shuffle(questions)

    # Return attempt with question IDs
    return {
        "id": attempt.id,
        "quiz_id": quiz.id,
        "user_id": current_user.id,
        "attempt_number": attempt.attempt_number,
        "started_at": attempt.created_at,
        "is_completed": False,
        "is_graded": False,
        "questions": questions,
    }


@router.post("/{quiz_id}/attempts/{attempt_id}/submit", response_model=QuizAttemptResponse)
async def submit_quiz_attempt(
        quiz_id: int = Path(..., description="The ID of the quiz"),
        attempt_id: int = Path(..., description="The ID of the attempt"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Submit a quiz attempt for grading
    """
    # Get quiz and attempt
    quiz = await Quiz.get_or_none(id=quiz_id)

    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    attempt = await QuizAttempt.get_or_none(id=attempt_id, quiz=quiz, user=current_user)

    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz attempt not found",
        )

    # Check if attempt is already completed
    if attempt.is_completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This quiz attempt is already completed",
        )

    # Mark attempt as completed
    attempt.is_completed = True
    attempt.submitted_at = datetime.utcnow()

    # Calculate time spent
    time_spent = (attempt.submitted_at - attempt.created_at).total_seconds()
    attempt.time_spent_seconds = int(time_spent)

    await attempt.save()

    # Automatically grade if possible
    await grade_quiz_attempt(quiz, attempt)

    # Get responses for the attempt
    responses = await QuizResponse.filter(attempt=attempt).prefetch_related("question").all()

    return {
        "id": attempt.id,
        "quiz_id": quiz.id,
        "user_id": current_user.id,
        "attempt_number": attempt.attempt_number,
        "score": attempt.score,
        "started_at": attempt.created_at,
        "submitted_at": attempt.submitted_at,
        "time_spent_seconds": attempt.time_spent_seconds,
        "is_completed": attempt.is_completed,
        "is_graded": attempt.is_graded,
        "responses": responses,
    }


@router.post("/{quiz_id}/attempts/{attempt_id}/responses", response_model=Dict[str, Any])
async def save_quiz_response(
        response_in: QuizResponseCreate,
        quiz_id: int = Path(..., description="The ID of the quiz"),
        attempt_id: int = Path(..., description="The ID of the attempt"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Save a response to a quiz question
    """
    # Get quiz and attempt
    quiz = await Quiz.get_or_none(id=quiz_id)

    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    attempt = await QuizAttempt.get_or_none(id=attempt_id, quiz=quiz, user=current_user)

    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz attempt not found",
        )

    # Check if attempt is already completed
    if attempt.is_completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This quiz attempt is already completed",
        )

    # Get question
    question = await Question.get_or_none(id=response_in.question_id)

    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )

    # Check if response already exists
    existing_response = await QuizResponse.get_or_none(attempt=attempt, question=question)

    if existing_response:
        # Update existing response
        if response_in.selected_answers is not None:
            # Clear existing selected answers
            await existing_response.selected_answers.clear()

            # Add new selected answers
            for answer_id in response_in.selected_answers:
                answer = await QuestionAnswer.get_or_none(id=answer_id, question=question)
                if answer:
                    await existing_response.selected_answers.add(answer)

        if response_in.text_response is not None:
            existing_response.text_response = response_in.text_response

        if response_in.numerical_response is not None:
            existing_response.numerical_response = response_in.numerical_response

        if response_in.file_response_id is not None:
            existing_response.file_response_id = response_in.file_response_id

        if response_in.matching_response is not None:
            existing_response.matching_response = response_in.matching_response

        if response_in.ordering_response is not None:
            existing_response.ordering_response = response_in.ordering_response

        await existing_response.save()
        response = existing_response
    else:
        # Create new response
        response = await QuizResponse.create(
            attempt=attempt,
            question=question,
            text_response=response_in.text_response,
            numerical_response=response_in.numerical_response,
            file_response_id=response_in.file_response_id,
            matching_response=response_in.matching_response,
            ordering_response=response_in.ordering_response,
        )

        # Add selected answers if provided
        if response_in.selected_answers:
            for answer_id in response_in.selected_answers:
                answer = await QuestionAnswer.get_or_none(id=answer_id, question=question)
                if answer:
                    await response.selected_answers.add(answer)

    return {"message": "Response saved successfully"}

# Helper function to grade a quiz attempt
async def grade_quiz_attempt(quiz: Quiz, attempt: QuizAttempt) -> None:
    """
    Grade a quiz attempt automatically where possible
    """
    # Get all responses for the attempt
    responses = await QuizResponse.filter(attempt=attempt).prefetch_related("question").all()

    total_points = 0
    earned_points = 0
    graded_count = 0

    for response in responses:
        question = response.question

        # Skip questions that need manual grading
        if question.question_type in [QuestionType.ESSAY, QuestionType.FILE_UPLOAD]:
            continue

        # Get quiz question for points
        quiz_question = await QuizQuestion.get_or_none(
            quiz=quiz,
            question=question
        )

        question_points = quiz_question.points if quiz_question and quiz_question.points else question.points
        total_points += question_points

        # Grade based on question type
        is_correct = False
        score = 0

        if question.question_type == QuestionType.MULTIPLE_CHOICE:
            # Get correct answer
            correct_answer = await QuestionAnswer.get_or_none(question=question, is_correct=True)
            selected_answers = await response.selected_answers.all()

            if correct_answer and selected_answers and correct_answer.id == selected_answers[0].id:
                is_correct = True
                score = question_points

        elif question.question_type == QuestionType.MULTIPLE_ANSWER:
            # Get all correct answers
            correct_answers = await QuestionAnswer.filter(question=question, is_correct=True).all()
            selected_answers = await response.selected_answers.all()

            # Check if selected answers match correct answers
            if len(correct_answers) == len(selected_answers):
                correct_ids = {a.id for a in correct_answers}
                selected_ids = {a.id for a in selected_answers}

                if correct_ids == selected_ids:
                    is_correct = True
                    score = question_points
                elif question.is_partial_credit:
                    # Calculate partial credit
                    correct_selected = len(correct_ids.intersection(selecte
