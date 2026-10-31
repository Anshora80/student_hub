"""
AI Student Hub — Quiz Engine Logic
Handles deterministic server-side answer evaluation, score calculation, and result packaging.
Guarantees that results cannot be tampered with from the client browser.
"""

from models import get_questions_for_quiz, get_question_by_id


def evaluate_quiz_submission(topic_id, submitted_answers):
    """
    Evaluates quiz answers purely on the server.
    submitted_answers: dict of {question_id_str: selected_option_str} e.g. {'1': 'B', '2': 'A'}
    
    Returns a dict containing:
    - total_questions
    - correct_count
    - incorrect_count
    - unanswered_count
    - score
    - percentage
    - answers_list (for database insertion)
    - detailed_results (for immediate result presentation)
    """
    # Fetch all active questions for the given topic
    questions = get_questions_for_quiz(topic_id)
    total_questions = len(questions)

    if total_questions == 0:
        return {
            "total_questions": 0,
            "correct_count": 0,
            "incorrect_count": 0,
            "unanswered_count": 0,
            "score": 0,
            "percentage": 0.0,
            "answers_list": [],
            "detailed_results": []
        }

    correct_count = 0
    incorrect_count = 0
    unanswered_count = 0
    answers_list = []
    detailed_results = []

    for q in questions:
        q_id = q['id']
        # Fetch question with correct_answer from DB
        full_question = get_question_by_id(q_id)
        expected_ans = full_question['correct_answer'].strip().upper()
        
        # User submission (key could be string or int)
        user_selection = submitted_answers.get(str(q_id)) or submitted_answers.get(q_id)
        
        if user_selection:
            user_selection = user_selection.strip().upper()
        else:
            user_selection = None

        if user_selection is None or user_selection == '':
            unanswered_count += 1
            is_correct = 0
        elif user_selection == expected_ans:
            correct_count += 1
            is_correct = 1
        else:
            incorrect_count += 1
            is_correct = 0

        # Data for DB insertion into attempt_answers
        answers_list.append({
            "question_id": q_id,
            "selected_answer": user_selection,
            "is_correct": is_correct
        })

        # Detailed breakdown for immediate view
        detailed_results.append({
            "question_id": q_id,
            "question_text": full_question['question_text'],
            "option_a": full_question['option_a'],
            "option_b": full_question['option_b'],
            "option_c": full_question['option_c'],
            "option_d": full_question['option_d'],
            "selected_answer": user_selection,
            "correct_answer": expected_ans,
            "is_correct": bool(is_correct),
            "explanation": full_question['explanation']
        })

    score = correct_count
    # Percentage formula = (Correct Answers / Total Questions) * 100 with zero division guard
    percentage = round((correct_count / total_questions) * 100, 2) if total_questions > 0 else 0.0

    return {
        "total_questions": total_questions,
        "correct_count": correct_count,
        "incorrect_count": incorrect_count,
        "unanswered_count": unanswered_count,
        "score": score,
        "percentage": percentage,
        "answers_list": answers_list,
        "detailed_results": detailed_results
    }
