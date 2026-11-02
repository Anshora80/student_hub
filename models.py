"""
AI Student Hub — Database Access Layer (Models)
Provides clean, parameterized functions for CRUD operations on Users, Subjects, Topics, Questions, and Quiz Attempts.
Protects against SQL Injection by always using parameterized queries.
"""

from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db_connection


# ==========================================
# 1. User Management Functions
# ==========================================

def get_user_by_email(email):
    """Fetches a single user record by email address (case-insensitive)."""
    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE LOWER(email) = LOWER(?)", 
        (email.strip(),)
    ).fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    """Fetches a user record by primary key id."""
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user


def create_user(name, email, password, role='student', course='BCA', semester=5):
    """
    Registers a new user with a securely hashed password.
    Returns (user_id, None) on success, or (None, error_message) on failure.
    """
    name = name.strip()
    email = email.strip().lower()
    
    if not name or not email or not password:
        return None, "All required fields must be filled."
    
    if len(password) < 6:
        return None, "Password must be at least 6 characters long."
    
    # Check if email already exists
    if get_user_by_email(email):
        return None, "An account with this email address already exists."
    
    password_hash = generate_password_hash(password)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, role, course, semester)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, email, password_hash, role, course, semester))
        conn.commit()
        user_id = cursor.lastrowid
        return user_id, None
    except Exception as e:
        conn.rollback()
        return None, f"Database error while creating user: {str(e)}"
    finally:
        conn.close()


def authenticate_user(email, password):
    """
    Verifies user credentials.
    Returns user record if valid, otherwise None.
    """
    user = get_user_by_email(email)
    if not user:
        return None
    
    if check_password_hash(user['password_hash'], password):
        return user
    return None


# ==========================================
# 2. Subject & Topic Management Functions
# ==========================================

def get_all_active_subjects():
    """Returns all active subjects with the count of active topics."""
    conn = get_db_connection()
    subjects = conn.execute("""
        SELECT s.*, COUNT(t.id) as topic_count
        FROM subjects s
        LEFT JOIN topics t ON s.id = t.subject_id AND t.is_active = 1
        WHERE s.is_active = 1
        GROUP BY s.id
        ORDER BY s.name ASC
    """).fetchall()
    conn.close()
    return subjects


def get_subject_by_id(subject_id):
    """Fetches a subject by id."""
    conn = get_db_connection()
    subject = conn.execute("SELECT * FROM subjects WHERE id = ?", (subject_id,)).fetchone()
    conn.close()
    return subject


def get_topics_by_subject(subject_id):
    """Returns all active topics under a given subject with question counts."""
    conn = get_db_connection()
    topics = conn.execute("""
        SELECT t.*, COUNT(q.id) as question_count
        FROM topics t
        LEFT JOIN questions q ON t.id = q.topic_id AND q.is_active = 1
        WHERE t.subject_id = ? AND t.is_active = 1
        GROUP BY t.id
        ORDER BY t.name ASC
    """, (subject_id,)).fetchall()
    conn.close()
    return topics


def get_topic_by_id(topic_id):
    """Fetches a topic by id with its subject details."""
    conn = get_db_connection()
    topic = conn.execute("""
        SELECT t.*, s.name as subject_name
        FROM topics t
        JOIN subjects s ON t.subject_id = s.id
        WHERE t.id = ?
    """, (topic_id,)).fetchone()
    conn.close()
    return topic


# ==========================================
# 3. Question & Quiz Functions
# ==========================================

def get_questions_for_quiz(topic_id, limit=None):
    """
    Retrieves active questions for a quiz under a specific topic.
    Returns list of questions without exposing correct_answer to the client.
    """
    conn = get_db_connection()
    query = "SELECT id, topic_id, question_text, option_a, option_b, option_c, option_d FROM questions WHERE topic_id = ? AND is_active = 1"
    params = [topic_id]
    
    if limit:
        query += " LIMIT ?"
        params.append(limit)
        
    questions = conn.execute(query, params).fetchall()
    conn.close()
    return questions


def get_question_by_id(question_id):
    """Fetches a single question including correct answer and explanation (for server evaluation)."""
    conn = get_db_connection()
    question = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    conn.close()
    return question


# ==========================================
# 4. Quiz Attempt & History Functions
# ==========================================

def save_quiz_attempt(user_id, topic_id, score, total_questions, percentage, answers_list):
    """
    Saves a completed quiz attempt and its individual answer breakdown in a single atomic transaction.
    answers_list: list of dicts [{'question_id': q_id, 'selected_answer': 'A', 'is_correct': 1}, ...]
    Returns attempt_id on success.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO quiz_attempts (user_id, topic_id, score, total_questions, percentage)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, topic_id, score, total_questions, percentage))
        attempt_id = cursor.lastrowid

        for item in answers_list:
            cursor.execute("""
                INSERT INTO attempt_answers (attempt_id, question_id, selected_answer, is_correct)
                VALUES (?, ?, ?, ?)
            """, (attempt_id, item['question_id'], item.get('selected_answer'), item['is_correct']))

        conn.commit()
        return attempt_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_attempt_by_id(attempt_id, user_id=None):
    """
    Fetches attempt summary. If user_id is provided, ensures only the owner can access it.
    """
    conn = get_db_connection()
    query = """
        SELECT qa.*, t.name as topic_name, s.name as subject_name, u.name as user_name
        FROM quiz_attempts qa
        JOIN topics t ON qa.topic_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        JOIN users u ON qa.user_id = u.id
        WHERE qa.id = ?
    """
    params = [attempt_id]
    if user_id:
        query += " AND qa.user_id = ?"
        params.append(user_id)
        
    attempt = conn.execute(query, params).fetchone()
    conn.close()
    return attempt


def get_attempt_details(attempt_id):
    """
    Fetches full answer breakdown for an attempt, joining questions for explanations.
    """
    conn = get_db_connection()
    details = conn.execute("""
        SELECT aa.*, q.question_text, q.option_a, q.option_b, q.option_c, q.option_d, 
               q.correct_answer, q.explanation
        FROM attempt_answers aa
        JOIN questions q ON aa.question_id = q.id
        WHERE aa.attempt_id = ?
        ORDER BY aa.id ASC
    """, (attempt_id,)).fetchall()
    conn.close()
    return details


def get_user_quiz_history(user_id, limit=20):
    """Fetches past quiz attempts for a student, ordered by most recent first."""
    conn = get_db_connection()
    history = conn.execute("""
        SELECT qa.*, t.name as topic_name, s.name as subject_name
        FROM quiz_attempts qa
        JOIN topics t ON qa.topic_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        WHERE qa.user_id = ?
        ORDER BY qa.attempted_at DESC
        LIMIT ?
    """, (user_id, limit)).fetchall()
    conn.close()
    return history


# ==========================================
# 5. User Document & PDF RAG Functions
# ==========================================

def create_user_document(user_id, title, original_filename, stored_filename, file_size, total_pages=1, total_chunks=0):
    """Inserts a new document record belonging to user_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_documents (user_id, title, original_filename, stored_filename, file_size, total_pages, total_chunks)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, title.strip(), original_filename, stored_filename, file_size, total_pages, total_chunks))
    doc_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def store_document_chunks(document_id, chunks_data):
    """
    Saves document chunks and optional vector embeddings.
    chunks_data: list of dicts [{'chunk_index': i, 'page_number': p, 'chunk_text': t, 'embedding_json': j}, ...]
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    for c in chunks_data:
        cursor.execute("""
            INSERT INTO document_chunks (document_id, chunk_index, page_number, chunk_text, embedding_json)
            VALUES (?, ?, ?, ?, ?)
        """, (document_id, c['chunk_index'], c['page_number'], c['chunk_text'], c.get('embedding_json')))
    # Update total_chunks count on user_documents
    cursor.execute("""
        UPDATE user_documents SET total_chunks = ? WHERE id = ?
    """, (len(chunks_data), document_id))
    conn.commit()
    conn.close()


def get_user_documents(user_id):
    """Retrieves all documents uploaded by a specific student."""
    conn = get_db_connection()
    docs = conn.execute("""
        SELECT ud.*, 
               (SELECT COUNT(*) FROM document_quizzes dq WHERE dq.document_id = ud.id) as question_count,
               (SELECT COUNT(*) FROM document_quiz_attempts dqa WHERE dqa.document_id = ud.id) as attempt_count,
               (SELECT MAX(dqa.percentage) FROM document_quiz_attempts dqa WHERE dqa.document_id = ud.id) as best_score
        FROM user_documents ud
        WHERE ud.user_id = ?
        ORDER BY ud.created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return docs


def get_document_by_id(doc_id, user_id=None):
    """Retrieves a single document with optional ownership verification."""
    conn = get_db_connection()
    query = "SELECT * FROM user_documents WHERE id = ?"
    params = [doc_id]
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    doc = conn.execute(query, params).fetchone()
    conn.close()
    return doc


def delete_user_document(doc_id, user_id):
    """Securely deletes a document and all related chunks/quizzes if owned by user_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    doc = conn.execute("SELECT * FROM user_documents WHERE id = ? AND user_id = ?", (doc_id, user_id)).fetchone()
    if not doc:
        conn.close()
        return False, "Document not found or access denied."

    cursor.execute("DELETE FROM user_documents WHERE id = ? AND user_id = ?", (doc_id, user_id))
    conn.commit()
    conn.close()
    return True, doc['stored_filename']


def get_document_quizzes_for_attempt(document_id, user_id, batch_number=1):
    """Retrieves quiz questions for a document batch."""
    conn = get_db_connection()
    questions = conn.execute("""
        SELECT id, document_id, question_text, option_a, option_b, option_c, option_d, batch_number
        FROM document_quizzes
        WHERE document_id = ? AND user_id = ? AND batch_number = ?
        ORDER BY id ASC
    """, (document_id, user_id, batch_number)).fetchall()
    conn.close()
    return questions


def save_document_quiz_attempt(doc_id, user_id, batch_number, score, total_questions, percentage, weak_areas_json, recommendations_text, answers_list):
    """Saves completed PDF quiz attempt and individual answers in an atomic transaction."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO document_quiz_attempts (
                document_id, user_id, batch_number, score, total_questions, percentage, weak_areas_json, recommendations_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (doc_id, user_id, batch_number, score, total_questions, percentage, weak_areas_json, recommendations_text))
        attempt_id = cursor.lastrowid

        for a in answers_list:
            cursor.execute("""
                INSERT INTO document_attempt_answers (attempt_id, quiz_question_id, selected_answer, is_correct)
                VALUES (?, ?, ?, ?)
            """, (attempt_id, a['question_id'], a.get('selected_answer'), a['is_correct']))

        conn.commit()
        return attempt_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_document_quiz_attempt(attempt_id, user_id=None):
    """Fetches attempt summary for a document quiz with user authorization check."""
    conn = get_db_connection()
    query = """
        SELECT dqa.*, ud.title as document_title, ud.original_filename, u.name as student_name
        FROM document_quiz_attempts dqa
        JOIN user_documents ud ON dqa.document_id = ud.id
        JOIN users u ON dqa.user_id = u.id
        WHERE dqa.id = ?
    """
    params = [attempt_id]
    if user_id:
        query += " AND dqa.user_id = ?"
        params.append(user_id)
    attempt = conn.execute(query, params).fetchone()
    conn.close()
    return attempt


def get_document_attempt_details(attempt_id):
    """Fetches answer breakdown with questions and explanations for document quiz attempt."""
    conn = get_db_connection()
    details = conn.execute("""
        SELECT daa.*, dq.question_text, dq.option_a, dq.option_b, dq.option_c, dq.option_d,
               dq.correct_answer, dq.explanation
        FROM document_attempt_answers daa
        JOIN document_quizzes dq ON daa.quiz_question_id = dq.id
        WHERE daa.attempt_id = ?
        ORDER BY daa.id ASC
    """, (attempt_id,)).fetchall()
    conn.close()
    return details

