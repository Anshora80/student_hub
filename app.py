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
import uuid
import json
from functools import wraps
from werkzeug.utils import secure_filename
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
import rag_engine

# Load environment configuration
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'bca_major_project_secret_key_2026')
app.config['DATABASE'] = os.getenv('DATABASE', 'student_hub.db')

# Upload & File Security Configurations
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads', 'documents')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024  # Max 12MB upload limit
ALLOWED_EXTENSIONS = {'pdf'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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
    user_documents = models.get_user_documents(user['id'])

    return render_template(
        'dashboard.html',
        user=user,
        overall_stats=overall_stats,
        subject_stats=subject_stats,
        recommendations=recommendations_data,
        recent_attempts=recent_attempts,
        user_documents=user_documents
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


@app.route('/admin/users')
@admin_required
def admin_users():
    """Directory of all registered students and administrators."""
    conn = get_db_connection()
    users_list = conn.execute("""
        SELECT u.*, 
               (SELECT COUNT(*) FROM quiz_attempts qa WHERE qa.user_id = u.id) as total_quizzes,
               (SELECT COUNT(*) FROM user_documents ud WHERE ud.user_id = u.id) as total_docs
        FROM users u
        ORDER BY u.created_at DESC
    """).fetchall()
    conn.close()
    return render_template('manage_users.html', users=users_list)


# ==========================================================
# Universal Document Hub & PDF RAG Routes (Any Sector / Syllabus)
# ==========================================================

@app.route('/my-documents')
@login_required
def my_documents():
    """Lists all syllabus notes and books uploaded by the current student."""
    documents = models.get_user_documents(session['user_id'])
    return render_template('my_documents.html', documents=documents)


@app.route('/my-documents/upload', methods=['POST'])
@login_required
def upload_document():
    """
    Handles secure PDF upload:
    - Validates MIME type and .pdf extension
    - Enforces file size limits
    - Extracts text and breaks it into overlapping semantic chunks
    - Generates vector embeddings / chunks index for precise RAG and dynamic quizzes
    """
    if 'document' not in request.files:
        flash('No file part in the upload request.', 'danger')
        return redirect(url_for('my_documents'))

    file = request.files['document']
    title = request.form.get('title', '').strip()

    if file.filename == '':
        flash('Please select a PDF file to upload.', 'warning')
        return redirect(url_for('my_documents'))

    if not allowed_file(file.filename):
        flash('Invalid file format. Only .pdf files are accepted for syllabus analysis.', 'danger')
        return redirect(url_for('my_documents'))

    # Security: Verify PDF magic bytes signature (%PDF-)
    header_bytes = file.read(5)
    file.seek(0)
    if header_bytes != b'%PDF-':
        flash('Invalid or corrupted PDF file. Security verification failed.', 'danger')
        return redirect(url_for('my_documents'))

    original_filename = secure_filename(file.filename)
    if not title:
        title = original_filename.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ').title()

    # Store with unique secure UUID prefix to prevent collisions or overwriting
    stored_filename = f"{uuid.uuid4().hex[:12]}_{original_filename}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)

    try:
        file.save(file_path)
        file_size = os.path.getsize(file_path)

        # Extract text and overlapping chunks with page tracking
        total_pages, chunks = rag_engine.extract_text_and_chunks_from_pdf(file_path)

        # Create document record
        doc_id = models.create_user_document(
            user_id=session['user_id'],
            title=title,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_size=file_size,
            total_pages=total_pages,
            total_chunks=len(chunks)
        )

        # Store chunks in database
        models.store_document_chunks(doc_id, chunks)

        # Generate initial Batch 1 of 10 high-yield MCQs from this PDF
        try:
            rag_engine.generate_dynamic_quiz_from_document(
                document_id=doc_id,
                user_id=session['user_id'],
                batch_number=1,
                count=10
            )
        except Exception as e:
            # Non-blocking if offline/quota
            pass

        flash(f"Successfully processed '{title}' ({total_pages} pages, {len(chunks)} chunks indexed). Top 10 dynamic quiz ready!", 'success')
        return redirect(url_for('document_detail', doc_id=doc_id))

    except Exception as e:
        # Cleanup uploaded file if processing failed
        if os.path.exists(file_path):
            os.remove(file_path)
        flash(f"Error processing PDF: {str(e)}", 'danger')
        return redirect(url_for('my_documents'))


@app.route('/document/<int:doc_id>')
@login_required
def document_detail(doc_id):
    """Document dashboard: View summary, chat with PDF, and take dynamic quizzes."""
    doc = models.get_document_by_id(doc_id, user_id=session['user_id'])
    if not doc:
        flash('Document not found or access denied.', 'danger')
        return redirect(url_for('my_documents'))

    conn = get_db_connection()
    attempts = conn.execute("""
        SELECT * FROM document_quiz_attempts
        WHERE document_id = ? AND user_id = ?
        ORDER BY attempted_at DESC
    """, (doc_id, session['user_id'])).fetchall()

    total_generated_questions = conn.execute("""
        SELECT COUNT(*) FROM document_quizzes
        WHERE document_id = ? AND user_id = ?
    """, (doc_id, session['user_id'])).fetchone()[0]

    max_batch = conn.execute("""
        SELECT COALESCE(MAX(batch_number), 1) FROM document_quizzes
        WHERE document_id = ? AND user_id = ?
    """, (doc_id, session['user_id'])).fetchone()[0]
    conn.close()

    return render_template(
        'document_detail.html',
        doc=doc,
        attempts=attempts,
        total_generated_questions=total_generated_questions,
        max_batch=max_batch
    )


@app.route('/document/<int:doc_id>/chat', methods=['POST'])
@login_required
def document_chat(doc_id):
    """Answers a student's conceptual question grounded strictly in their uploaded PDF."""
    doc = models.get_document_by_id(doc_id, user_id=session['user_id'])
    if not doc:
        return jsonify({"error": "Document not found or access denied."}), 403

    query = request.form.get('query', '').strip()
    if not query:
        return jsonify({"error": "Please enter a valid question."}), 400

    response = rag_engine.answer_question_from_document(
        document_id=doc_id,
        doc_title=doc['title'],
        question_text=query
    )
    return jsonify(response)


@app.route('/document/<int:doc_id>/quiz')
@login_required
def document_quiz(doc_id):
    """Interactive quiz interface for a specific PDF batch."""
    doc = models.get_document_by_id(doc_id, user_id=session['user_id'])
    if not doc:
        flash('Document not found or access denied.', 'danger')
        return redirect(url_for('my_documents'))

    batch_number = request.args.get('batch', 1, type=int)

    # Fetch questions for this batch
    questions = models.get_document_quizzes_for_attempt(doc_id, session['user_id'], batch_number)

    # If questions do not exist yet for this batch, generate them dynamically
    if not questions:
        try:
            questions = rag_engine.generate_dynamic_quiz_from_document(
                document_id=doc_id,
                user_id=session['user_id'],
                batch_number=batch_number,
                count=10
            )
        except Exception as e:
            flash(f"Could not generate questions: {str(e)}", 'warning')
            return redirect(url_for('document_detail', doc_id=doc_id))

    return render_template(
        'document_quiz.html',
        doc=doc,
        questions=questions,
        batch_number=batch_number
    )


@app.route('/document/<int:doc_id>/quiz/submit', methods=['POST'])
@login_required
def submit_document_quiz(doc_id):
    """
    Evaluates PDF quiz submission on the server:
    - Compares submitted choices against database keys
    - Calculates score & percentage
    - Generates Weak Area & Learning Pattern insights
    - Saves audit trail
    """
    doc = models.get_document_by_id(doc_id, user_id=session['user_id'])
    if not doc:
        flash('Document not found.', 'danger')
        return redirect(url_for('my_documents'))

    batch_number = request.form.get('batch_number', 1, type=int)

    # Fetch all questions for this batch
    conn = get_db_connection()
    questions = conn.execute("""
        SELECT * FROM document_quizzes
        WHERE document_id = ? AND user_id = ? AND batch_number = ?
        ORDER BY id ASC
    """, (doc_id, session['user_id'], batch_number)).fetchall()
    conn.close()

    if not questions:
        flash('No questions found for this quiz batch.', 'danger')
        return redirect(url_for('document_detail', doc_id=doc_id))

    correct_count = 0
    incorrect_list = []
    answers_list = []

    for q in questions:
        q_id = q['id']
        expected_ans = q['correct_answer'].strip().upper()
        user_choice = request.form.get(f'question_{q_id}', '').strip().upper()

        if user_choice == expected_ans:
            is_correct = 1
            correct_count += 1
        else:
            is_correct = 0
            incorrect_list.append({
                "question_text": q['question_text'],
                "selected_answer": user_choice or "Unanswered",
                "correct_answer": expected_ans,
                "explanation": q['explanation']
            })

        answers_list.append({
            "question_id": q_id,
            "selected_answer": user_choice or None,
            "is_correct": is_correct
        })

    total_q = len(questions)
    percentage = round((correct_count / total_q) * 100, 2) if total_q > 0 else 0.0

    # Generate Weak Area & Learning Pattern Analysis
    weak_analysis_text = rag_engine.analyze_document_quiz_performance(
        doc_title=doc['title'],
        score=correct_count,
        total_questions=total_q,
        percentage=percentage,
        incorrect_list=incorrect_list
    )

    # Save attempt
    attempt_id = models.save_document_quiz_attempt(
        doc_id=doc_id,
        user_id=session['user_id'],
        batch_number=batch_number,
        score=correct_count,
        total_questions=total_q,
        percentage=percentage,
        weak_areas_json=json.dumps([item['question_text'][:80] for item in incorrect_list]),
        recommendations_text=weak_analysis_text,
        answers_list=answers_list
    )

    flash('Quiz evaluated and saved! Review your weak areas and learning pattern below.', 'success')
    return redirect(url_for('view_document_quiz_result', attempt_id=attempt_id))


@app.route('/document/<int:doc_id>/quiz/next')
@login_required
def next_document_quiz_batch(doc_id):
    """
    Generates the next batch of 10 fresh questions from the PDF,
    guaranteeing no repeats of previously asked questions.
    """
    doc = models.get_document_by_id(doc_id, user_id=session['user_id'])
    if not doc:
        flash('Document not found.', 'danger')
        return redirect(url_for('my_documents'))

    conn = get_db_connection()
    current_max_batch = conn.execute("""
        SELECT COALESCE(MAX(batch_number), 0) FROM document_quizzes
        WHERE document_id = ? AND user_id = ?
    """, (doc_id, session['user_id'])).fetchone()[0]
    conn.close()

    next_batch = current_max_batch + 1

    try:
        new_questions = rag_engine.generate_dynamic_quiz_from_document(
            document_id=doc_id,
            user_id=session['user_id'],
            batch_number=next_batch,
            count=10
        )
        if not new_questions:
            flash(f"You have already explored all primary questions for '{doc['title']}'! Retaking existing batches is recommended.", 'info')
            return redirect(url_for('document_detail', doc_id=doc_id))

        flash(f"Generated Next 10 Questions (Batch {next_batch}) from your document!", 'success')
        return redirect(url_for('document_quiz', doc_id=doc_id, batch=next_batch))

    except Exception as e:
        flash(f"Error generating next batch: {str(e)}", 'danger')
        return redirect(url_for('document_detail', doc_id=doc_id))


@app.route('/document/quiz-result/<int:attempt_id>')
@login_required
def view_document_quiz_result(attempt_id):
    """Displays PDF quiz results with Weak Area and Learning Pattern diagnostic guidance."""
    attempt = models.get_document_quiz_attempt(attempt_id, user_id=session['user_id'])
    if not attempt:
        flash('Quiz attempt not found or access denied.', 'danger')
        return redirect(url_for('my_documents'))

    answers = models.get_document_attempt_details(attempt_id)

    return render_template(
        'document_quiz_result.html',
        attempt=attempt,
        answers=answers
    )


@app.route('/document/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete_document(doc_id):
    """Deletes an uploaded document and removes physical file."""
    success, filename_or_msg = models.delete_user_document(doc_id, session['user_id'])
    if success:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename_or_msg)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        flash('Document and associated quizzes deleted successfully.', 'info')
    else:
        flash(filename_or_msg, 'danger')
    return redirect(url_for('my_documents'))



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
