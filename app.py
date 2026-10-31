"""
AI Student Hub — Main Application & Route Controller
=====================================================
A complete, secure, role-based Flask application integrating:
- Student Registration, Login & Session Management
- Protected Routes & Role-Based Access Control
- Dynamic Subjects, Topics, and MCQ Question Banks
- Server-Side Quiz Engine with Tamper-Proof Evaluation
- Performance Analytics & Rule-Based Recommendation Engine
- Administrative Management Controls
"""

import os
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, 
    url_for, session, flash, abort, jsonify
)
from dotenv import load_dotenv

from database import get_db_connection, init_db
import models
import quiz_logic
import recommendation
import ai_assistant

# Load environment configuration
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'bca_major_project_secret_key_2026')
app.config['DATABASE'] = os.getenv('DATABASE', 'student_hub.db')


# ==========================================================
# Authentication & Authorization Decorators
# ==========================================================

def login_required(f):
    """
    Decorator to ensure user is logged in before accessing protected routes.
    Redirects to login page if unauthenticated.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    Decorator to restrict access exclusively to users with 'admin' role.
    Prevents students from accessing administrative pages.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Please log in with administrator privileges.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Access Denied: You do not have permission to view administrator pages.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# ==========================================================
# Public Routes (Landing, Health)
# ==========================================================

@app.route('/')
def index():
    """Public home landing page."""
    return render_template('index.html')


@app.route('/health')
def health():
    """Health check endpoint for status monitoring."""
    return jsonify({
        "status": "healthy",
        "app": "AI Student Hub",
        "version": "1.0.0"
    })


# ==========================================================
# Authentication Routes (Register, Login, Logout)
# ==========================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handles student account registration."""
    if session.get('user_id'):
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        course = request.form.get('course', 'BCA').strip()
        semester = request.form.get('semester', 5)
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Server-side validations
        if not name or not email or not password:
            flash('All required fields must be filled.', 'danger')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match. Please verify and try again.', 'danger')
            return render_template('register.html')

        if len(password) < 6:
            flash('Password must contain at least 6 characters.', 'danger')
            return render_template('register.html')

        user_id, error = models.create_user(
            name=name,
            email=email,
            password=password,
            role='student',
            course=course,
            semester=int(semester) if str(semester).isdigit() else 5
        )

        if error:
            flash(error, 'danger')
            return render_template('register.html')

        flash('Registration successful! Please sign in with your credentials.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles authentication for both Students and Administrators."""
    if session.get('user_id'):
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please enter both your email address and password.', 'danger')
            return render_template('login.html')

        user = models.authenticate_user(email, password)

        if not user:
            flash('Invalid email address or password. Please try again.', 'danger')
            return render_template('login.html')

        # Store user details securely in session
        session.clear()
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']
        session['role'] = user['role']

        flash(f"Welcome back, {user['name']}!", 'success')

        if user['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Clears user session and logs out."""
    session.clear()
    flash('You have been logged out safely.', 'info')
    return redirect(url_for('login'))


# ==========================================================
# Student Learning & Assessment Routes
# ==========================================================

@app.route('/dashboard')
@login_required
def dashboard():
    """Student central learning dashboard with live analytics and rule-based suggestions."""
    user = models.get_user_by_id(session['user_id'])
    overall_stats = recommendation.get_student_overall_stats(user['id'])
    subject_stats = recommendation.get_student_subject_performance(user['id'])
    recommendations_data = recommendation.generate_personalized_recommendations(user['id'])
    recent_attempts = models.get_user_quiz_history(user['id'], limit=5)

    return render_template(
        'dashboard.html',
        user=user,
        overall_stats=overall_stats,
        subject_stats=subject_stats,
        recommendations=recommendations_data,
        recent_attempts=recent_attempts
    )


@app.route('/subjects')
@login_required
def subjects():
    """Lists all active academic subjects."""
    all_subjects = models.get_all_active_subjects()
    return render_template('subjects.html', subjects=all_subjects)


@app.route('/subjects/<int:subject_id>/topics')
@login_required
def view_topics(subject_id):
    """Lists all active topics under a selected subject."""
    subject = models.get_subject_by_id(subject_id)
    if not subject:
        flash('Requested subject not found.', 'danger')
        return redirect(url_for('subjects'))

    topics = models.get_topics_by_subject(subject_id)
    return render_template('topics.html', subject=subject, topics=topics)


@app.route('/quiz/<int:topic_id>')
@login_required
def start_quiz(topic_id):
    """Renders the quiz interface for a specific topic."""
    topic = models.get_topic_by_id(topic_id)
    if not topic:
        flash('Topic not found.', 'danger')
        return redirect(url_for('subjects'))

    questions = models.get_questions_for_quiz(topic_id)
    if not questions:
        flash('No active questions are currently available for this topic.', 'warning')
        return redirect(url_for('view_topics', subject_id=topic['subject_id']))

    return render_template('quiz.html', topic=topic, questions=questions)


@app.route('/quiz/<int:topic_id>/submit', methods=['POST'])
@login_required
def submit_quiz(topic_id):
    """
    Evaluates quiz submission securely on the backend.
    Saves attempt record and redirects to detailed performance result.
    """
    topic = models.get_topic_by_id(topic_id)
    if not topic:
        flash('Topic not found.', 'danger')
        return redirect(url_for('subjects'))

    # Extract user answers from form (question_1: 'A', question_2: 'C')
    submitted_answers = {}
    for key, value in request.form.items():
        if key.startswith('question_'):
            q_id = key.split('_')[1]
            submitted_answers[q_id] = value

    # Server-side answer evaluation
    eval_result = quiz_logic.evaluate_quiz_submission(topic_id, submitted_answers)

    # Persist attempt and answers atomically
    attempt_id = models.save_quiz_attempt(
        user_id=session['user_id'],
        topic_id=topic_id,
        score=eval_result['score'],
        total_questions=eval_result['total_questions'],
        percentage=eval_result['percentage'],
        answers_list=eval_result['answers_list']
    )

    flash('Quiz evaluated and saved successfully!', 'success')
    return redirect(url_for('view_result', attempt_id=attempt_id))


@app.route('/result/<int:attempt_id>')
@login_required
def view_result(attempt_id):
    """
    Displays full result breakdown of a specific attempt with concept explanations.
    Guarantees authorization: students can only access their own results (admins can audit all).
    Integrates AI Study Assistant for personalized diagnostics and 3-step action roadmap.
    """
    user_id = None if session.get('role') == 'admin' else session.get('user_id')
    attempt = models.get_attempt_by_id(attempt_id, user_id=user_id)

    if not attempt:
        flash('Result not found or you are not authorized to view this record.', 'danger')
        return redirect(url_for('dashboard'))

    answers = models.get_attempt_details(attempt_id)
    incorrect_items = [a for a in answers if not a['is_correct']]

    # Generate AI diagnostic study plan
    ai_analysis = ai_assistant.generate_ai_attempt_analysis(
        student_name=attempt['user_name'],
        subject_name=attempt['subject_name'],
        topic_name=attempt['topic_name'],
        score=attempt['score'],
        total_questions=attempt['total_questions'],
        percentage=attempt['percentage'],
        incorrect_items=incorrect_items
    )

    return render_template('result.html', attempt=attempt, answers=answers, ai_analysis=ai_analysis)


@app.route('/ai-tutor', methods=['GET', 'POST'])
@login_required
def ai_tutor():
    """Interactive AI Concept Tutor allowing students to ask syllabus and coding questions."""
    ai_response = None
    user_query = ""
    selected_topic = ""

    conn = get_db_connection()
    topics = conn.execute("""
        SELECT t.id, t.name, s.name as subject_name 
        FROM topics t 
        JOIN subjects s ON t.subject_id = s.id 
        WHERE t.is_active = 1
        ORDER BY s.name ASC, t.name ASC
    """).fetchall()
    conn.close()

    if request.method == 'POST':
        user_query = request.form.get('query', '').strip()
        selected_topic = request.form.get('topic', '').strip()

        if user_query:
            ai_response = ai_assistant.ask_ai_concept_tutor(user_query, selected_topic)
        else:
            flash('Please type a question to ask the AI Tutor.', 'warning')

    return render_template(
        'ai_tutor.html', 
        ai_response=ai_response, 
        user_query=user_query, 
        selected_topic=selected_topic, 
        topics=topics
    )


@app.route('/history')
@login_required
def history_view():
    """Displays student's historical quiz attempt logs."""
    history = models.get_user_quiz_history(session['user_id'], limit=50)
    return render_template('history.html', history=history)


@app.route('/performance')
@login_required
def performance_view():
    """Displays comprehensive subject and topic-wise performance breakdown."""
    user_id = session['user_id']
    subject_stats = recommendation.get_student_subject_performance(user_id)
    topic_metrics = recommendation.get_student_topic_performance(user_id)
    return render_template('performance.html', subject_stats=subject_stats, topic_metrics=topic_metrics)


@app.route('/recommendations')
@login_required
def recommendations_view():
    """Displays rule-based learning recommendations and study roadmaps."""
    user_id = session['user_id']
    rec = recommendation.generate_personalized_recommendations(user_id)
    return render_template('recommendations.html', rec=rec)


# ==========================================================
# Administrator Routes (Role Protected)
# ==========================================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Main administrative dashboard with platform statistics."""
    conn = get_db_connection()
    total_students = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'student'").fetchone()[0]
    total_subjects = conn.execute("SELECT COUNT(*) FROM subjects WHERE is_active = 1").fetchone()[0]
    total_topics = conn.execute("SELECT COUNT(*) FROM topics WHERE is_active = 1").fetchone()[0]
    total_questions = conn.execute("SELECT COUNT(*) FROM questions WHERE is_active = 1").fetchone()[0]
    total_attempts = conn.execute("SELECT COUNT(*) FROM quiz_attempts").fetchone()[0]
    conn.close()

    stats = {
        "total_students": total_students,
        "total_subjects": total_subjects,
        "total_topics": total_topics,
        "total_questions": total_questions,
        "total_attempts": total_attempts
    }
    return render_template('admin_dashboard.html', stats=stats)


@app.route('/admin/subjects', methods=['GET', 'POST'])
@admin_required
def admin_subjects():
    """Create and manage curriculum subjects."""
    conn = get_db_connection()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not name:
            flash('Subject name cannot be empty.', 'danger')
        else:
            try:
                conn.execute("INSERT INTO subjects (name, description) VALUES (?, ?)", (name, description))
                conn.commit()
                flash(f"Subject '{name}' created successfully!", 'success')
            except Exception as e:
                flash(f"Error creating subject: {str(e)}", 'danger')

    subjects_list = conn.execute("""
        SELECT s.*, COUNT(t.id) as topic_count
        FROM subjects s
        LEFT JOIN topics t ON s.id = t.subject_id AND t.is_active = 1
        GROUP BY s.id
        ORDER BY s.name ASC
    """).fetchall()
    conn.close()

    return render_template('manage_subjects.html', subjects=subjects_list)


@app.route('/admin/topics', methods=['GET', 'POST'])
@admin_required
def admin_topics():
    """Create and manage syllabus topics."""
    conn = get_db_connection()
    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not subject_id or not name:
            flash('Parent subject and topic name are required.', 'danger')
        else:
            try:
                conn.execute(
                    "INSERT INTO topics (subject_id, name, description) VALUES (?, ?, ?)",
                    (subject_id, name, description)
                )
                conn.commit()
                flash(f"Topic '{name}' created successfully!", 'success')
            except Exception as e:
                flash(f"Error creating topic: {str(e)}", 'danger')

    subjects_list = conn.execute("SELECT id, name FROM subjects WHERE is_active = 1 ORDER BY name ASC").fetchall()
    topics_list = conn.execute("""
        SELECT t.*, s.name as subject_name, COUNT(q.id) as question_count
        FROM topics t
        JOIN subjects s ON t.subject_id = s.id
        LEFT JOIN questions q ON t.id = q.topic_id AND q.is_active = 1
        GROUP BY t.id
        ORDER BY s.name ASC, t.name ASC
    """).fetchall()
    conn.close()

    return render_template('manage_topics.html', subjects=subjects_list, topics=topics_list)


@app.route('/admin/questions', methods=['GET', 'POST'])
@admin_required
def admin_questions():
    """Create and manage MCQ question bank."""
    conn = get_db_connection()
    if request.method == 'POST':
        topic_id = request.form.get('topic_id')
        question_text = request.form.get('question_text', '').strip()
        opt_a = request.form.get('option_a', '').strip()
        opt_b = request.form.get('option_b', '').strip()
        opt_c = request.form.get('option_c', '').strip()
        opt_d = request.form.get('option_d', '').strip()
        correct_answer = request.form.get('correct_answer', '').strip().upper()
        explanation = request.form.get('explanation', '').strip()

        if not all([topic_id, question_text, opt_a, opt_b, opt_c, opt_d, correct_answer]):
            flash('All question fields and options must be completed.', 'danger')
        else:
            try:
                conn.execute("""
                    INSERT INTO questions (topic_id, question_text, option_a, option_b, option_c, option_d, correct_answer, explanation)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (topic_id, question_text, opt_a, opt_b, opt_c, opt_d, correct_answer, explanation))
                conn.commit()
                flash('New MCQ added to question bank successfully!', 'success')
            except Exception as e:
                flash(f"Error creating question: {str(e)}", 'danger')

    topics_list = conn.execute("""
        SELECT t.id, t.name, s.name as subject_name 
        FROM topics t 
        JOIN subjects s ON t.subject_id = s.id 
        WHERE t.is_active = 1 
        ORDER BY s.name ASC, t.name ASC
    """).fetchall()

    questions_list = conn.execute("""
        SELECT q.*, t.name as topic_name, s.name as subject_name
        FROM questions q
        JOIN topics t ON q.topic_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        ORDER BY q.id DESC
    """).fetchall()
    conn.close()

    return render_template('manage_questions.html', topics=topics_list, questions=questions_list)


@app.route('/admin/results')
@admin_required
def admin_student_results():
    """Platform-wide audit of all student quiz attempts."""
    conn = get_db_connection()
    attempts = conn.execute("""
        SELECT qa.*, u.name as student_name, u.email as student_email,
               t.name as topic_name, s.name as subject_name
        FROM quiz_attempts qa
        JOIN users u ON qa.user_id = u.id
        JOIN topics t ON qa.topic_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        ORDER BY qa.attempted_at DESC
    """).fetchall()
    conn.close()
    return render_template('student_results.html', attempts=attempts)


# ==========================================================
# Error Handlers
# ==========================================================

@app.errorhandler(404)
def page_not_found(e):
    return render_template('base.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return "An internal server error occurred.", 500


if __name__ == '__main__':
    # Initialize database on app startup if not present
    init_db()
    app.run(host='127.0.0.1', port=5000, debug=True)
