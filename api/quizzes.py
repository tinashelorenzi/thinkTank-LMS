from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, BackgroundTasks

from models.course import Course
from models.users import User, UserRole
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
                    correct_selected = len(correct_ids.intersection(selected_ids))
                    incorrect_selected = len(selected_ids - correct_ids)
                    total_correct = len(correct_ids)
                    total_possible_incorrect = len(await QuestionAnswer.filter(question=question).all()) - total_correct

                    # Calculate score percentage
                    correct_ratio = correct_selected / total_correct if total_correct > 0 else 0
                    incorrect_penalty = incorrect_selected / total_possible_incorrect if total_possible_incorrect > 0 else 0
                    score_percent = max(0, correct_ratio - incorrect_penalty)

                    score = question_points * score_percent
                    is_correct = score > 0
                elif question.question_type == QuestionType.TRUE_FALSE:
                    correct_answer = await QuestionAnswer.get_or_none(question=question, is_correct=True)
                    selected_answers = await response.selected_answers.all()
                    if correct_answer and selected_answers and correct_answer.id == selected_answers[0].id:
                        is_correct = True
                        score = question_points
                    elif question.question_type == QuestionType.NUMERICAL:
                        if response.numerical_response is not None and question.numerical_answer is not None:
                            # Check within tolerance
                            tolerance = question.numerical_tolerance or 0
                            if abs(response.numerical_response - question.numerical_answer) <= tolerance:
                                is_correct = True
                                score = question_points

                    elif question.question_type == QuestionType.MATCHING:
                        # Check matching answers
                        if response.matching_response and question.matching_pairs:
                            # Convert matching_pairs to a dict for easier comparison
                            correct_matches = {}
                            for pair in question.matching_pairs:
                                correct_matches[pair["left"]] = pair["right"]

                            # Count correct matches
                            correct_count = 0
                            for left, right in response.matching_response.items():
                                if left in correct_matches and correct_matches[left] == right:
                                    correct_count += 1
                            # Calculate score
                            if correct_count == len(correct_matches):
                                is_correct = True
                                score = question_points
                            elif question.is_partial_credit:
                                # Partial credit based on correct matches
                                score_percent = correct_count / len(correct_matches)
                                score = question_points * score_percent
                                is_correct = score > 0
                    elif question.question_type == QuestionType.ORDERING:
                        # Check ordering
                        if response.ordering_response and question.correct_order:
                            if response.ordering_response == question.correct_order:
                                is_correct = True
                                score = question_points
                            elif question.is_partial_credit:
                                # Calculate longest common subsequence as partial credit
                                lcs_length = longest_common_subsequence(response.ordering_response, question.correct_order)
                                score_percent = lcs_length / len(question.correct_order)
                                score = question_points * score_percent
                                is_correct = score > 0

                    elif question.question_type == QuestionType.FILL_IN_BLANK:
                        # Check text response against correct answers
                        if response.text_response:
                            # Get all correct answers
                            correct_answers = await QuestionAnswer.filter(question=question, is_correct=True).all()

                            # Check if response matches any correct answer
                            for answer in correct_answers:
                                if response.text_response.strip().lower() == answer.text.strip().lower():
                                    is_correct = True
                                    score = question_points
                                    break

                    elif question.question_type == QuestionType.SHORT_ANSWER:
                        # Similar to fill in blank but with more flexibility
                        if response.text_response:
                            # Get all correct answers
                            correct_answers = await QuestionAnswer.filter(question=question, is_correct=True).all()

                            # Check if response contains any correct answer as substring
                            for answer in correct_answers:
                                if answer.text.strip().lower() in response.text_response.strip().lower():
                                    is_correct = True
                                    score = question_points
                                    break

                    # Update response with score and feedback
                    response.score = score
                    response.is_correct = is_correct

                    # Add feedback based on correctness
                    if question.feedback:
                        response.feedback = question.feedback

                    await response.save()

                    # Add to total
                    earned_points += score
                    graded_count += 1

                # Update attempt with score if all questions are graded
                if graded_count > 0:
                    attempt.score = earned_points / total_points * 100 if total_points > 0 else 0
                    attempt.is_graded = True
                    await attempt.save()

# Helper function for calculating longest common subsequence
def longest_common_subsequence(seq1, seq2):
    """Calculate the length of the longest common subsequence of two sequences"""
    m, n = len(seq1), len(seq2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if seq1[i-1] == seq2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])

    return dp[m][n]


@router.get("/{quiz_id}/attempts", response_model=List[QuizAttemptResponse])
async def list_quiz_attempts(
        quiz_id: int = Path(..., description="The ID of the quiz"),
        user_id: Optional[int] = Query(None, description="Filter by user ID"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    List attempts for a quiz
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

    # Create base query
    query = QuizAttempt.filter(quiz=quiz)

    # Filter by user
    # Instructors can view all attempts, students can only view their own
    if current_user.role == UserRole.ADMIN:
        if user_id:
            query = query.filter(user_id=user_id)
    elif current_user.role == UserRole.INSTRUCTOR:
        # Check if user is instructor of the course
        is_instructor = await Enrollment.filter(
            user=current_user,
            course=quiz.course,
            type=EnrollmentType.TEACHER,
            state=EnrollmentState.ACTIVE,
        ).exists()

        if is_instructor:
            if user_id:
                query = query.filter(user_id=user_id)
        else:
            # If not instructor, can only see own attempts
            query = query.filter(user=current_user)
    else:
        # Students can only view their own attempts
        query = query.filter(user=current_user)

    # Get attempts ordered by latest first
    attempts = await query.order_by("-created_at").prefetch_related("user").all()

    # Format response
    result = []
    for attempt in attempts:
        # Get responses for the attempt
        responses = await QuizResponse.filter(attempt=attempt).prefetch_related("question").all()

        result.append({
            "id": attempt.id,
            "quiz_id": quiz.id,
            "user_id": attempt.user.id,
            "attempt_number": attempt.attempt_number,
            "score": attempt.score,
            "started_at": attempt.created_at,
            "submitted_at": attempt.submitted_at,
            "time_spent_seconds": attempt.time_spent_seconds,
            "is_completed": attempt.is_completed,
            "is_graded": attempt.is_graded,
            "responses": responses,
        })

    return result


@router.get("/{quiz_id}/attempts/{attempt_id}", response_model=QuizAttemptResponse)
async def get_quiz_attempt(
        quiz_id: int = Path(..., description="The ID of the quiz"),
        attempt_id: int = Path(..., description="The ID of the attempt"),
        current_user: User = Depends(get_current_active_user),
) -> Any:
    """
    Get a specific quiz attempt
    """
    # Get quiz and attempt
    quiz = await Quiz.get_or_none(id=quiz_id)

    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    attempt = await QuizAttempt.get_or_none(id=attempt_id, quiz=quiz).prefetch_related("user")

    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz attempt not found",
        )

    # Check if user has permission to view this attempt
    if current_user.role != UserRole.ADMIN:
        # Users can view their own attempts
        if attempt.user_id != current_user.id:
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
                    detail="You do not have permission to view this attempt",
                )

    # Get responses for the attempt
    responses = await QuizResponse.filter(attempt=attempt).prefetch_related("question").all()

    # Show correct answers and feedback only if appropriate
    show_answers = False

    if current_user.role == UserRole.ADMIN or current_user.role == UserRole.INSTRUCTOR:
        show_answers = True
    elif attempt.is_completed:
        # Check quiz settings for showing correct answers
        if quiz.show_correct_answers:
            # Check time restrictions
            now = datetime.utcnow()

            if (quiz.show_correct_answers_at is None or now >= quiz.show_correct_answers_at) and \
                    (quiz.hide_correct_answers_at is None or now <= quiz.hide_correct_answers_at):
                show_answers = True

    # Format responses based on permissions
    for response in responses:
        if not show_answers:
            # Hide correct/incorrect status and feedback
            response.is_correct = None
            response.feedback = None

    return {
        "id": attempt.id,
        "quiz_id": quiz.id,
        "user_id": attempt.user.id,
        "attempt_number": attempt.attempt_number,
        "score": attempt.score,
        "started_at": attempt.created_at,
        "submitted_at": attempt.submitted_at,
        "time_spent_seconds": attempt.time_spent_seconds,
        "is_completed": attempt.is_completed,
        "is_graded": attempt.is_graded,
        "responses": responses,
    }


@router.post("/questions/{question_id}/answers", response_model=Dict[str, Any])
async def add_question_answer(
        question_id: int = Path(..., description="The ID of the question"),
        text: str = Query(..., description="Answer text"),
        is_correct: bool = Query(False, description="Whether this answer is correct"),
        weight: float = Query(100.0, description="Weight for partial credit"),
        feedback: Optional[str] = Query(None, description="Feedback for this answer"),
        match_id: Optional[str] = Query(None, description="ID for matching questions"),
        order_position: Optional[int] = Query(None, description="Position for ordering questions"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Add an answer to a question (instructor or admin only)
    """
    # Get question
    question = await Question.get_or_none(id=question_id)

    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )

    # Create answer
    answer = await QuestionAnswer.create(
        text=text,
        question=question,
        is_correct=is_correct,
        weight=weight,
        feedback=feedback,
        match_id=match_id,
        order_position=order_position,
    )

    return {
        "id": answer.id,
        "text": answer.text,
        "is_correct": answer.is_correct,
        "weight": answer.weight,
        "feedback": answer.feedback,
        "match_id": answer.match_id,
        "order_position": answer.order_position,
    }


@router.delete("/questions/answers/{answer_id}", response_model=Dict[str, Any])
async def delete_question_answer(
        answer_id: int = Path(..., description="The ID of the answer"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Delete an answer from a question (instructor or admin only)
    """
    # Get answer
    answer = await QuestionAnswer.get_or_none(id=answer_id).prefetch_related("question")

    if not answer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Answer not found",
        )

    # Delete answer
    await answer.delete()

    return {"message": "Answer deleted successfully"}


@router.post("/{quiz_id}/questions", response_model=Dict[str, Any])
async def add_question_to_quiz(
        quiz_id: int = Path(..., description="The ID of the quiz"),
        question_id: int = Query(..., description="ID of the question to add"),
        position: Optional[int] = Query(None, description="Position in the quiz"),
        points: Optional[float] = Query(None, description="Points for this question in the quiz"),
        question_group_id: Optional[int] = Query(None, description="ID of question group (if any)"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Add an existing question to a quiz (instructor or admin only)
    """
    # Get quiz
    quiz = await Quiz.get_or_none(id=quiz_id).prefetch_related("course")

    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    # Check if user has permission to modify this quiz
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
                detail="You do not have permission to modify this quiz",
            )

    # Get question
    question = await Question.get_or_none(id=question_id)

    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )

    # Get question group if specified
    question_group = None
    if question_group_id:
        question_group = await QuizQuestionGroup.get_or_none(id=question_group_id, quiz=quiz)

        if not question_group:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question group not found",
            )

    # Check if question is already in the quiz
    existing_question = await QuizQuestion.get_or_none(
        quiz=quiz,
        question=question,
    )

    if existing_question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question is already in this quiz",
        )

    # Determine position if not provided
    if position is None:
        if question_group:
            # Get max position in group
            max_position_result = await QuizQuestion.filter(
                quiz=quiz,
                question_group=question_group
            ).order_by("-position").first()

            position = (max_position_result.position + 1) if max_position_result else 0
        else:
            # Get max position in quiz
            max_position_result = await QuizQuestion.filter(
                quiz=quiz,
                question_group=None
            ).order_by("-position").first()

            position = (max_position_result.position + 1) if max_position_result else 0

    # Create quiz question
    quiz_question = await QuizQuestion.create(
        quiz=quiz,
        question=question,
        position=position,
        points=points,
        question_group=question_group,
    )

    # Update quiz stats
    quiz.question_count += 1
    quiz.points_possible += points or question.points
    await quiz.save()

    return {
        "id": quiz_question.id,
        "quiz_id": quiz.id,
        "question_id": question.id,
        "position": quiz_question.position,
        "points": quiz_question.points,
        "question_group_id": question_group_id,
    }


@router.delete("/{quiz_id}/questions/{quiz_question_id}", response_model=Dict[str, Any])
async def remove_question_from_quiz(
        quiz_id: int = Path(..., description="The ID of the quiz"),
        quiz_question_id: int = Path(..., description="The ID of the quiz question"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Remove a question from a quiz (instructor or admin only)
    """
    # Get quiz
    quiz = await Quiz.get_or_none(id=quiz_id).prefetch_related("course")

    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    # Check if user has permission to modify this quiz
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
                detail="You do not have permission to modify this quiz",
            )

    # Get quiz question
    quiz_question = await QuizQuestion.get_or_none(id=quiz_question_id, quiz=quiz).prefetch_related("question")

    if not quiz_question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found in this quiz",
        )

    # Update quiz stats
    question_points = quiz_question.points or quiz_question.question.points
    quiz.question_count = max(0, quiz.question_count - 1)
    quiz.points_possible = max(0, quiz.points_possible - question_points)
    await quiz.save()

    # Delete quiz question
    await quiz_question.delete()

    return {"message": "Question removed from quiz successfully"}


@router.post("/{quiz_id}/question-groups", response_model=Dict[str, Any])
async def create_question_group(
        quiz_id: int = Path(..., description="The ID of the quiz"),
        title: Optional[str] = Query(None, description="Group title"),
        position: int = Query(0, description="Position in the quiz"),
        pick_count: int = Query(1, description="Number of questions to pick from the group"),
        points_per_question: Optional[float] = Query(None, description="Points per question in the group"),
        question_bank_id: Optional[int] = Query(None, description="Question bank to pull questions from"),
        current_user: User = Depends(get_current_instructor_or_admin),
) -> Any:
    """
    Create a question group in a quiz (instructor or admin only)
    """
    # Get quiz
    quiz = await Quiz.get_or_none(id=quiz_id).prefetch_related("course")

    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found",
        )

    # Check if user has permission to modify this quiz
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
                detail="You do not have permission to modify this quiz",
            )

    # Check question bank if specified
    if question_bank_id:
        question_bank = await QuestionBank.get_or_none(id=question_bank_id)

        if not question_bank:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Question bank not found",
            )

    # Create question group
    group = await QuizQuestionGroup.create(
        quiz=quiz,
        title=title,
        position=position,
        pick_count=pick_count,
        points_per_question=points_per_question,
        question_bank_id=question_bank_id,
    )

    return {
        "id": group.id,
        "quiz_id": quiz.id,
        "title": group.title,
        "position": group.position,
        "pick_count": group.pick_count,
        "points_per_question": group.points_per_question,
        "question_bank_id": group.question_bank_id,
    }

