"""
AI Student Hub — Performance Analytics & Recommendation Engine
Provides deterministic, rule-based learning analytics and personalized study recommendations
based on stored quiz attempts.
"""

from database import get_db_connection

# Configurable Performance Thresholds (can be adjusted by faculty/admins)
THRESHOLD_MASTERY = 80.0     # 80% and above -> Mastered
THRESHOLD_COMPETENT = 60.0   # 60% to 79.9% -> Competent / Additional Practice


def get_student_overall_stats(user_id):
    """
    Computes overall summary statistics for a student:
    - Total quizzes attempted
    - Overall average percentage
    - Total correct answers vs total questions attempted
    """
    conn = get_db_connection()
    stats = conn.execute("""
        SELECT 
            COUNT(id) as total_attempts,
            COALESCE(AVG(percentage), 0.0) as average_percentage,
            COALESCE(SUM(score), 0) as total_correct,
            COALESCE(SUM(total_questions), 0) as total_questions
        FROM quiz_attempts
        WHERE user_id = ?
    """, (user_id,)).fetchone()
    conn.close()

    total_attempts = stats['total_attempts'] or 0
    avg_pct = round(stats['average_percentage'], 2) if total_attempts > 0 else 0.0

    return {
        "total_attempts": total_attempts,
        "average_percentage": avg_pct,
        "total_correct": stats['total_correct'] or 0,
        "total_questions": stats['total_questions'] or 0,
        "has_data": total_attempts > 0
    }


def get_student_subject_performance(user_id):
    """
    Calculates subject-wise average scores and attempt counts for a student.
    Returns list of dicts ordered by average percentage descending.
    """
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT 
            s.id as subject_id,
            s.name as subject_name,
            COUNT(qa.id) as attempts_count,
            COALESCE(AVG(qa.percentage), 0.0) as avg_percentage
        FROM subjects s
        JOIN topics t ON s.id = t.subject_id
        JOIN quiz_attempts qa ON t.id = qa.topic_id
        WHERE qa.user_id = ?
        GROUP BY s.id
        ORDER BY avg_percentage DESC
    """, (user_id,)).fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "subject_id": r["subject_id"],
            "subject_name": r["subject_name"],
            "attempts_count": r["attempts_count"],
            "avg_percentage": round(r["avg_percentage"], 2)
        })
    return results


def get_student_topic_performance(user_id):
    """
    Calculates topic-wise accuracy metrics across all attempts for a given student.
    Classifies each topic using configurable threshold rules.
    """
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT 
            t.id as topic_id,
            t.name as topic_name,
            s.name as subject_name,
            COUNT(qa.id) as attempts_count,
            COALESCE(AVG(qa.percentage), 0.0) as avg_percentage,
            MAX(qa.attempted_at) as last_attempted
        FROM topics t
        JOIN subjects s ON t.subject_id = s.id
        LEFT JOIN quiz_attempts qa ON t.id = qa.topic_id AND qa.user_id = ?
        WHERE t.is_active = 1
        GROUP BY t.id
        ORDER BY s.name ASC, t.name ASC
    """, (user_id,)).fetchall()
    conn.close()

    topic_metrics = []
    for r in rows:
        attempts = r["attempts_count"]
        avg_pct = round(r["avg_percentage"], 2) if attempts > 0 else 0.0
        
        # Determine status and category
        if attempts == 0:
            status = "Unattempted"
            badge_class = "badge-neutral"
            recommendation_level = "NEW"
        elif avg_pct < THRESHOLD_COMPETENT:
            status = "Priority Practice"
            badge_class = "badge-danger"
            recommendation_level = "PRIORITY"
        elif avg_pct < THRESHOLD_MASTERY:
            status = "Needs Practice"
            badge_class = "badge-warning"
            recommendation_level = "PRACTICE"
        else:
            status = "Mastered"
            badge_class = "badge-success"
            recommendation_level = "MASTERED"

        topic_metrics.append({
            "topic_id": r["topic_id"],
            "topic_name": r["topic_name"],
            "subject_name": r["subject_name"],
            "attempts_count": attempts,
            "avg_percentage": avg_pct,
            "status": status,
            "badge_class": badge_class,
            "recommendation_level": recommendation_level,
            "last_attempted": r["last_attempted"]
        })

    return topic_metrics


def generate_personalized_recommendations(user_id):
    """
    Generates intelligent, actionable study recommendations based on actual performance.
    Categorizes topics into:
    - Priority Practice Topics (Score < 60%)
    - Revision Topics (60% <= Score < 80%)
    - Mastered Topics (Score >= 80%)
    - Unattempted Topics to Explore
    """
    topic_metrics = get_student_topic_performance(user_id)
    overall_stats = get_student_overall_stats(user_id)

    priority_topics = []
    practice_topics = []
    mastered_topics = []
    unattempted_topics = []

    for t in topic_metrics:
        if t["attempts_count"] == 0:
            unattempted_topics.append(t)
        elif t["avg_percentage"] < THRESHOLD_COMPETENT:
            priority_topics.append(t)
        elif t["avg_percentage"] < THRESHOLD_MASTERY:
            practice_topics.append(t)
        else:
            mastered_topics.append(t)

    # Sort priority topics by lowest score first
    priority_topics.sort(key=lambda x: x["avg_percentage"])
    # Sort practice topics by lowest score first
    practice_topics.sort(key=lambda x: x["avg_percentage"])

    # Determine recommended next step
    if not overall_stats["has_data"]:
        recommended_next_action = "Start your first quiz in 'Variables and Data Types' to establish your baseline skill level."
        focus_topic = unattempted_topics[0] if unattempted_topics else None
    elif priority_topics:
        focus_topic = priority_topics[0]
        recommended_next_action = f"Focus urgently on '{focus_topic['topic_name']}' ({focus_topic['subject_name']}). Your average score is {focus_topic['avg_percentage']}%. Review fundamental concepts and retake the quiz."
    elif practice_topics:
        focus_topic = practice_topics[0]
        recommended_next_action = f"Strengthen your understanding of '{focus_topic['topic_name']}' ({focus_topic['subject_name']}). Practice edge cases to elevate your score beyond 80%."
    elif unattempted_topics:
        focus_topic = unattempted_topics[0]
        recommended_next_action = f"Great work mastering attempted topics! Move forward by attempting '{focus_topic['topic_name']}' in {focus_topic['subject_name']}."
    else:
        focus_topic = None
        recommended_next_action = "Outstanding mastery across all available topics! Revisit topics periodically for retention."

    return {
        "overall_stats": overall_stats,
        "priority_topics": priority_topics,
        "practice_topics": practice_topics,
        "mastered_topics": mastered_topics,
        "unattempted_topics": unattempted_topics,
        "recommended_next_action": recommended_next_action,
        "focus_topic": focus_topic,
        "thresholds": {
            "mastery": THRESHOLD_MASTERY,
            "competent": THRESHOLD_COMPETENT
        }
    }
