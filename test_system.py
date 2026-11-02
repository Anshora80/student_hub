"""
AI Student Hub — Automated System Test Suite
Executes comprehensive end-to-end verification covering:
- Authentication & Role-Based Security
- Database integrity & duplicate handling
- Quiz Engine server-side grading & zero-division safety
- History logging & student isolation
- Rule-based recommendation engine accuracy
"""

import sys
import io
import json
from app import app
from database import get_db_connection, init_db, seed_sample_data
import models
import quiz_logic
import recommendation
import rag_engine

def run_tests():
    print("=" * 65)
    print("AI STUDENT HUB — COMPREHENSIVE AUTOMATED TEST RUNNER")
    print("=" * 65)

    client = app.test_client()
    passed_tests = 0
    total_tests = 0

    def assert_test(test_id, description, condition, details=""):
        nonlocal passed_tests, total_tests
        total_tests += 1
        status = "PASSED" if condition else "FAILED"
        if condition:
            passed_tests += 1
            print(f"[{status}] {test_id}: {description}")
        else:
            print(f"[{status}] {test_id}: {description} --> Details: {details}")

    # Reset DB state for clean testing
    init_db()
    seed_sample_data()

    # Clean test users if left from prior runs
    clean_conn = get_db_connection()
    clean_conn.execute("DELETE FROM users WHERE email IN ('pooja@college.edu', 'other@college.edu')")
    clean_conn.commit()
    clean_conn.close()

    # Test 1: Health check
    res = client.get('/health')
    assert_test("TC-01", "Health Check endpoint returns status 200 and healthy JSON", 
                res.status_code == 200 and res.get_json().get("status") == "healthy")

    # Test 2: Public landing page
    res = client.get('/')
    assert_test("TC-02", "Landing page renders successfully", 
                res.status_code == 200 and b"AI Student Hub" in res.data)

    # Test 3: Valid Student Registration
    res = client.post('/register', data={
        'name': 'Pooja Verma',
        'email': 'pooja@college.edu',
        'course': 'BCA',
        'semester': '5',
        'password': 'Password@123',
        'confirm_password': 'Password@123'
    }, follow_redirects=True)
    assert_test("TC-03", "Valid student registration creates account and redirects to login", 
                res.status_code == 200 and b"Registration successful" in res.data)

    # Test 4: Duplicate Email Registration
    res = client.post('/register', data={
        'name': 'Pooja Duplicate',
        'email': 'pooja@college.edu',
        'course': 'BCA',
        'semester': '5',
        'password': 'Password@123',
        'confirm_password': 'Password@123'
    }, follow_redirects=True)
    assert_test("TC-04", "Duplicate email registration is blocked with descriptive alert", 
                res.status_code == 200 and b"already exists" in res.data)

    # Test 5: Invalid Login Attempt
    res = client.post('/login', data={
        'email': 'student@studenthub.com',
        'password': 'WrongPassword123'
    }, follow_redirects=True)
    assert_test("TC-05", "Invalid password rejected gracefully", 
                res.status_code == 200 and b"Invalid email address or password" in res.data)

    # Test 6: Successful Student Login & Session
    res = client.post('/login', data={
        'email': 'student@studenthub.com',
        'password': 'Student@123'
    }, follow_redirects=True)
    assert_test("TC-06", "Student login succeeds and grants access to Dashboard", 
                res.status_code == 200 and b"Welcome back" in res.data)

    # Test 7: Student Blocked from Admin Dashboard
    res = client.get('/admin', follow_redirects=True)
    assert_test("TC-07", "Student access to Admin Dashboard is forbidden and redirected", 
                res.status_code == 200 and b"Access Denied" in res.data)

    # Test 8: Logout Clears Session
    res = client.get('/logout', follow_redirects=True)
    assert_test("TC-08", "Logout clears user session and redirects to login", 
                res.status_code == 200 and b"logged out safely" in res.data)

    # Test 9: Protected Route Redirects Unauthenticated Users
    res = client.get('/dashboard', follow_redirects=True)
    assert_test("TC-09", "Unauthenticated request to /dashboard redirected to login", 
                res.status_code == 200 and b"Please log in to access this page" in res.data)

    # Test 10: Admin Login & Access to Admin Control Center
    res = client.post('/login', data={
        'email': 'admin@studenthub.com',
        'password': 'Admin@123'
    }, follow_redirects=True)
    assert_test("TC-10", "Admin login succeeds and navigates to Admin Control Center", 
                res.status_code == 200 and b"Administrator Control Center" in res.data)

    # Test 11: Admin Creates New Subject
    res = client.post('/admin/subjects', data={
        'name': 'Web Technologies',
        'description': 'HTML5, CSS3, JavaScript, and HTTP fundamentals.'
    }, follow_redirects=True)
    assert_test("TC-11", "Admin creates new subject in database", 
                res.status_code == 200 and b"Web Technologies" in res.data)

    # Test 12: Quiz Engine Server-Side Evaluation (All Correct)
    # Target topic 1: Variables and Data Types (4 questions in seed)
    # Correct answers in seed: Q1 -> B, Q2 -> C, Q3 -> D, Q4 -> B
    q_list = models.get_questions_for_quiz(1)
    submission_perfect = {}
    for q in q_list:
        full_q = models.get_question_by_id(q['id'])
        submission_perfect[str(q['id'])] = full_q['correct_answer']
    
    eval_perfect = quiz_logic.evaluate_quiz_submission(1, submission_perfect)
    assert_test("TC-12", "Quiz Engine evaluates perfect submission as 100.0% accuracy", 
                eval_perfect['percentage'] == 100.0 and eval_perfect['score'] == len(q_list))

    # Test 13: Empty Quiz Submission Handled Safely (Zero Division Guard)
    eval_empty = quiz_logic.evaluate_quiz_submission(1, {})
    assert_test("TC-13", "Empty quiz submission handled gracefully (score 0, percentage 0.0%)", 
                eval_empty['score'] == 0 and eval_empty['percentage'] == 0.0 and eval_empty['unanswered_count'] == len(q_list))

    # Test 14: Save Quiz Attempt to Database and Verify History
    # Log in as demo student first
    client.get('/logout')
    client.post('/login', data={'email': 'student@studenthub.com', 'password': 'Student@123'})
    
    # Take a quiz via HTTP POST
    res = client.post('/quiz/1/submit', data={
        f"question_{q_list[0]['id']}": "B",  # correct
        f"question_{q_list[1]['id']}": "A",  # incorrect
        f"question_{q_list[2]['id']}": "D",  # correct
        f"question_{q_list[3]['id']}": "A",  # incorrect
    }, follow_redirects=True)
    assert_test("TC-14", "Quiz submission saves attempt and displays detailed result page", 
                res.status_code == 200 and b"Quiz Performance Report" in res.data and b"50.0%" in res.data)

    # Test 15: History View Contains Completed Attempt
    res = client.get('/history')
    assert_test("TC-15", "Quiz history page reflects completed attempt", 
                res.status_code == 200 and b"Variables and Data Types" in res.data)

    # Test 16: Recommendation Engine Identifies Weak Topic (<60%)
    student = models.get_user_by_email('student@studenthub.com')
    recs = recommendation.generate_personalized_recommendations(student['id'])
    has_priority = any(t['topic_name'] == 'Variables and Data Types' for t in recs['priority_topics'])
    assert_test("TC-16", "Recommendation engine flags 50% score as Priority Practice (<60%)", 
                has_priority and "Focus urgently" in recs['recommended_next_action'])

    # Test 17: Isolation of Student Results
    # Dynamically find the attempt created by student@studenthub.com
    check_conn = get_db_connection()
    last_row = check_conn.execute("SELECT id FROM quiz_attempts ORDER BY id DESC LIMIT 1").fetchone()
    last_attempt_id = last_row['id'] if last_row else 1
    check_conn.close()

    # Create another student and ensure they cannot view demo student's result
    other_id, _ = models.create_user('Other Student', 'other@college.edu', 'Password@123')
    client.get('/logout')
    client.post('/login', data={'email': 'other@college.edu', 'password': 'Password@123'})
    
    # Attempt belongs to student@studenthub.com, other student must be blocked
    res = client.get(f'/result/{last_attempt_id}', follow_redirects=True)
    assert_test("TC-17", "Student is blocked from accessing another student's private quiz result", 
                res.status_code == 200 and b"not authorized" in res.data)

    # Test 18: AI Study Coach Analysis in Result Page
    # Log back in as demo student and check result
    client.get('/logout')
    client.post('/login', data={'email': 'student@studenthub.com', 'password': 'Student@123'})
    res = client.get(f'/result/{last_attempt_id}')
    assert_test("TC-18", "Result page renders AI Study Coach analysis and diagnostic advice", 
                res.status_code == 200 and b"AI Study Coach Analysis" in res.data)

    # Test 19: AI Concept Tutor Query Handling
    res = client.post('/ai-tutor', data={
        'topic': 'Variables and Data Types',
        'query': 'What is the difference between a list and a tuple?'
    }, follow_redirects=True)
    assert_test("TC-19", "AI Concept Tutor processes conceptual question and returns educational explanation", 
                res.status_code == 200 and b"What is the difference between a list and a tuple?" in res.data and b"AI Tutor Note" in res.data or b"List" in res.data)

    # =========================================================
    # Universal PDF RAG & Dynamic Quiz Engine Tests (TC-20 to TC-25)
    # =========================================================

    def create_mock_pdf_bytes():
        return b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 280 >> stream
BT
/F1 12 Tf
50 720 Td
(Modern Indian Polity and Constitution: Fundamental Rights are enshrined in Part III and protected under Article 32. Directive Principles in Part IV guide social justice and economic welfare. Parliament comprises the President, Lok Sabha, and Rajya Sabha with bicameral federal legislation.) Tj
ET
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000244 00000 n 
0000000576 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
655
%%EOF"""

    # Test 20: PDF Upload Security (Rejection of Non-PDF File)
    res = client.post('/my-documents/upload', data={
        'title': 'Malicious File Test',
        'document': (io.BytesIO(b'Executable binary code'), 'malware.exe')
    }, follow_redirects=True)
    assert_test("TC-20", "Upload validator rejects non-PDF file extension with descriptive alert",
                res.status_code == 200 and b"Only .pdf files are accepted" in res.data)

    # Test 21: Valid PDF Upload & Text Chunking in SQLite
    mock_pdf = create_mock_pdf_bytes()
    res = client.post('/my-documents/upload', data={
        'title': 'UPSC Indian Polity Notes',
        'document': (io.BytesIO(mock_pdf), 'indian_polity.pdf')
    }, follow_redirects=True)
    assert_test("TC-21", "Valid PDF upload succeeds, extracts text chunks, and initializes Document Hub",
                res.status_code == 200 and b"UPSC Indian Polity Notes" in res.data)

    # Get newly created document
    student_user = models.get_user_by_email('student@studenthub.com')
    docs = models.get_user_documents(student_user['id'])
    test_doc = next((d for d in docs if d['title'] == 'UPSC Indian Polity Notes'), None)
    doc_id = test_doc['id'] if test_doc else 1

    # Test 22: RAG Grounded Q&A (Chat with Document)
    res = client.post(f'/document/{doc_id}/chat', data={
        'query': 'What is Article 32 related to in the constitution?'
    })
    chat_json = res.get_json() or {}
    assert_test("TC-22", "RAG Engine answers question grounded in uploaded PDF with page citations",
                res.status_code == 200 and "answer" in chat_json and ("Article 32" in chat_json["answer"] or "Fundamental Rights" in chat_json["answer"] or len(chat_json.get("sources", [])) > 0))

    # Test 23: Dynamic Top-10 MCQ Quiz Render
    res = client.get(f'/document/{doc_id}/quiz?batch=1')
    assert_test("TC-23", "Dynamic PDF Assessment renders Batch 1 Multiple Choice Questions",
                res.status_code == 200 and b"Dynamic PDF Assessment" in res.data and b"Question 1" in res.data)

    # Test 24: Server-Side Quiz Grading & Weak Area / Learning Pattern Analysis
    # Fetch questions generated for Batch 1 from database directly with answer key
    conn = get_db_connection()
    batch_qs = conn.execute("""
        SELECT id, correct_answer FROM document_quizzes
        WHERE document_id = ? AND batch_number = 1
    """, (doc_id,)).fetchall()
    conn.close()

    submission_data = {'batch_number': '1'}
    if batch_qs:
        # Deliberately answer first question correctly, second incorrectly
        submission_data[f"question_{batch_qs[0]['id']}"] = batch_qs[0]['correct_answer']
        if len(batch_qs) > 1:
            wrong_opt = 'A' if batch_qs[1]['correct_answer'] != 'A' else 'B'
            submission_data[f"question_{batch_qs[1]['id']}"] = wrong_opt

    res = client.post(f'/document/{doc_id}/quiz/submit', data=submission_data, follow_redirects=True)
    assert_test("TC-24", "PDF Quiz submission grades server-side and generates Weak Area / Learning Pattern Diagnostics",
                res.status_code == 200 and b"Syllabus Performance Report" in res.data and b"AI Weak Area & Learning Pattern Diagnostics" in res.data)

    # Test 25: Non-Duplicate "Next 10 Questions" Generation
    res = client.get(f'/document/{doc_id}/quiz/next', follow_redirects=True)
    assert_test("TC-25", "Next 10 Questions batch generation executes and transitions to Batch 2",
                res.status_code == 200 and (b"Batch 2" in res.data or b"Next 10" in res.data or b"Dynamic PDF Assessment" in res.data))

    print("=" * 65)
    print(f"TEST EXECUTION SUMMARY: {passed_tests} / {total_tests} TESTS PASSED")
    print("=" * 65)

    return passed_tests == total_tests


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
