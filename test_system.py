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
from app import app
from database import get_db_connection, init_db, seed_sample_data
import models
import quiz_logic
import recommendation

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

    print("=" * 65)
    print(f"TEST EXECUTION SUMMARY: {passed_tests} / {total_tests} TESTS PASSED")
    print("=" * 65)

    return passed_tests == total_tests

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
