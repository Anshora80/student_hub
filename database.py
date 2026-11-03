"""
AI Student Hub — Database Management Module
Handles SQLite schema creation, foreign key enforcement, connection pooling, and sample data seeding.
"""

import sqlite3
import os
from werkzeug.security import generate_password_hash

# Database file path
DB_NAME = os.getenv('DATABASE', 'student_hub.db')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, DB_NAME)


def get_db_connection():
    """
    Creates and returns a SQLite database connection with row factory enabled,
    foreign key constraints enforced, WAL mode for production concurrency,
    and a 30-second timeout to prevent lock contentions.
    """
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    # Enable accessing columns by name like dictionary keys: row['email']
    conn.row_factory = sqlite3.Row
    # Enforce foreign key constraints in SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    # Set WAL mode for smooth concurrent reads and writes
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except Exception:
        pass
    return conn


def init_db():
    """
    Initializes all database tables with proper relational constraints.
    Creates tables if they do not exist.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Users Table (Students & Administrators)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student' CHECK(role IN ('student', 'admin')),
            course TEXT DEFAULT 'BCA',
            semester INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. Subjects Table (e.g. Python, DSA, DBMS)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1))
        );
    """)

    # 3. Topics Table (Belongs to a Subject)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        );
    """)

    # 4. Questions Table (Multiple-choice questions belonging to a Topic)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_answer TEXT NOT NULL CHECK(correct_answer IN ('A', 'B', 'C', 'D')),
            explanation TEXT,
            is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
            FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
        );
    """)

    # 5. Quiz Attempts Table (High-level summary of a student's quiz session)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            topic_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            percentage REAL NOT NULL,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
        );
    """)

    # 6. Attempt Answers Table (Audit trail of individual question responses)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attempt_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            selected_answer TEXT CHECK(selected_answer IN ('A', 'B', 'C', 'D') OR selected_answer IS NULL),
            is_correct INTEGER NOT NULL CHECK(is_correct IN (0, 1)),
            FOREIGN KEY (attempt_id) REFERENCES quiz_attempts(id) ON DELETE CASCADE,
            FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
        );
    """)

    # 7. User Documents Table (Uploaded Syllabi, Notes, Question Banks - Any Sector)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            stored_filename TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            total_pages INTEGER DEFAULT 1,
            total_chunks INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)

    # 8. Document Chunks Table (Chunked text & embeddings for RAG)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            page_number INTEGER DEFAULT 1,
            chunk_text TEXT NOT NULL,
            embedding_json TEXT,
            FOREIGN KEY (document_id) REFERENCES user_documents(id) ON DELETE CASCADE
        );
    """)

    # 9. Document Generated Quizzes (Dynamic MCQs generated by AI from PDF)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            question_text TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            correct_answer TEXT NOT NULL CHECK(correct_answer IN ('A', 'B', 'C', 'D')),
            explanation TEXT,
            question_hash TEXT NOT NULL,
            batch_number INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES user_documents(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)

    # 10. Document Quiz Attempts (Results for PDF-based quizzes)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            batch_number INTEGER DEFAULT 1,
            score INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            percentage REAL NOT NULL,
            weak_areas_json TEXT,
            recommendations_text TEXT,
            attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES user_documents(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
    """)

    # 11. Document Attempt Answers (Audit trail of PDF quiz responses)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_attempt_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attempt_id INTEGER NOT NULL,
            quiz_question_id INTEGER NOT NULL,
            selected_answer TEXT CHECK(selected_answer IN ('A', 'B', 'C', 'D') OR selected_answer IS NULL),
            is_correct INTEGER NOT NULL CHECK(is_correct IN (0, 1)),
            FOREIGN KEY (attempt_id) REFERENCES document_quiz_attempts(id) ON DELETE CASCADE,
            FOREIGN KEY (quiz_question_id) REFERENCES document_quizzes(id) ON DELETE CASCADE
        );
    """)

    conn.commit()
    conn.close()
    print("Database tables initialized successfully.")


def seed_sample_data():
    """
    Seeds initial demonstration data into SQLite database:
    - Default Admin & Student user accounts
    - Core Subjects (Python Programming, DSA, DBMS)
    - Sub-topics for each subject
    - Realistic MCQs with 4 options and detailed explanations.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # --- 1. Seed Users ---
    # Default Admin
    cursor.execute("SELECT id FROM users WHERE email = ?", ('admin@studenthub.com',))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, role, course, semester)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'Admin User',
            'admin@studenthub.com',
            generate_password_hash('Admin@123'),
            'admin',
            'Faculty/Admin',
            0
        ))
        print("Demo Admin seeded: admin@studenthub.com / Admin@123")

    # Default Demo Student
    cursor.execute("SELECT id FROM users WHERE email = ?", ('student@studenthub.com',))
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, role, course, semester)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'Rahul Sharma',
            'student@studenthub.com',
            generate_password_hash('Student@123'),
            'student',
            'BCA',
            5
        ))
        print("Demo Student seeded: student@studenthub.com / Student@123")

    # --- 2. Seed Subjects and Topics ---
    subjects_data = [
        {
            "name": "Python Programming",
            "description": "Core concepts of Python, data structures, functions, and OOP.",
            "topics": [
                {
                    "name": "Variables and Data Types",
                    "description": "Integers, strings, floats, booleans, and type casting in Python.",
                    "questions": [
                        {
                            "text": "What will be the output of `type(5 / 2)` in Python 3?",
                            "a": "<class 'int'>",
                            "b": "<class 'float'>",
                            "c": "<class 'double'>",
                            "d": "<class 'number'>",
                            "ans": "B",
                            "exp": "In Python 3, the single slash `/` operator always performs float division, producing 2.5."
                        },
                        {
                            "text": "Which of the following data types is IMMUTABLE in Python?",
                            "a": "List",
                            "b": "Dictionary",
                            "c": "Tuple",
                            "d": "Set",
                            "ans": "C",
                            "exp": "Tuples and strings cannot be modified after creation, making them immutable."
                        },
                        {
                            "text": "How do you declare a single-line comment in Python?",
                            "a": "// comment",
                            "b": "/* comment */",
                            "c": "<!-- comment -->",
                            "d": "# comment",
                            "ans": "D",
                            "exp": "In Python, the hash symbol `#` starts a single-line comment."
                        },
                        {
                            "text": "What is the result of `bool('False')` in Python?",
                            "a": "False",
                            "b": "True",
                            "c": "None",
                            "d": "TypeError",
                            "ans": "B",
                            "exp": "Any non-empty string in Python evaluates to True in boolean context."
                        }
                    ]
                },
                {
                    "name": "Loops and Control Flow",
                    "description": "If-else conditions, while loops, for loops, and break/continue statements.",
                    "questions": [
                        {
                            "text": "What does the `break` keyword do inside a loop?",
                            "a": "Skips the current iteration and continues with the next",
                            "b": "Terminates the loop entirely",
                            "c": "Restarts the loop from the beginning",
                            "d": "Exits the entire Python program",
                            "ans": "B",
                            "exp": "`break` terminates the nearest enclosing loop immediately."
                        },
                        {
                            "text": "What is the output of `list(range(2, 7, 2))`?",
                            "a": "[2, 4, 6]",
                            "b": "[2, 3, 4, 5, 6]",
                            "c": "[2, 5, 7]",
                            "d": "[4, 6]",
                            "ans": "A",
                            "exp": "range(start, stop, step) starts at 2, increments by 2, and stops before 7 -> [2, 4, 6]."
                        },
                        {
                            "text": "Which keyword is used to skip the rest of the current iteration and move to the next iteration?",
                            "a": "pass",
                            "b": "skip",
                            "c": "continue",
                            "d": "next",
                            "ans": "C",
                            "exp": "`continue` skips the remaining statements of the current loop iteration."
                        }
                    ]
                },
                {
                    "name": "Functions and Scope",
                    "description": "Defining functions, arguments, return values, and variable scope.",
                    "questions": [
                        {
                            "text": "Which keyword is used to define a function in Python?",
                            "a": "function",
                            "b": "func",
                            "c": "def",
                            "d": "define",
                            "ans": "C",
                            "exp": "`def` is the Python keyword used to define a function."
                        },
                        {
                            "text": "What does a function return by default if no return statement is specified?",
                            "a": "0",
                            "b": "False",
                            "c": "None",
                            "d": "Empty String",
                            "ans": "C",
                            "exp": "In Python, a function without an explicit return statement returns `None`."
                        }
                    ]
                }
            ]
        },
        {
            "name": "Data Structures & Algorithms",
            "description": "Linear and non-linear data structures, searching, and sorting techniques.",
            "topics": [
                {
                    "name": "Arrays and Linear Search",
                    "description": "Array operations, indexing, and linear searching time complexity.",
                    "questions": [
                        {
                            "text": "What is the worst-case time complexity of Linear Search on an array of size N?",
                            "a": "O(1)",
                            "b": "O(log N)",
                            "c": "O(N)",
                            "d": "O(N^2)",
                            "ans": "C",
                            "exp": "In the worst case (element at end or not present), linear search checks all N elements: O(N)."
                        },
                        {
                            "text": "What is the index of the first element in standard Python lists or arrays?",
                            "a": "-1",
                            "b": "0",
                            "c": "1",
                            "d": "None",
                            "ans": "B",
                            "exp": "Python uses 0-based indexing for lists and sequences."
                        }
                    ]
                },
                {
                    "name": "Stacks and Queues",
                    "description": "LIFO stack and FIFO queue fundamentals and applications.",
                    "questions": [
                        {
                            "text": "Which principle does a Stack data structure follow?",
                            "a": "FIFO (First In First Out)",
                            "b": "LIFO (Last In First Out)",
                            "c": "LILO (Last In Last Out)",
                            "d": "Priority Based",
                            "ans": "B",
                            "exp": "Stack follows Last In First Out (LIFO), like a stack of plates."
                        },
                        {
                            "text": "Which principle does a standard Queue data structure follow?",
                            "a": "FIFO (First In First Out)",
                            "b": "LIFO (Last In First Out)",
                            "c": "Random Access",
                            "d": "None of the above",
                            "ans": "A",
                            "exp": "Queue follows First In First Out (FIFO), like people standing in a ticket queue."
                        }
                    ]
                }
            ]
        },
        {
            "name": "Database Management Systems",
            "description": "Relational databases, SQL queries, normalization, and ACID properties.",
            "topics": [
                {
                    "name": "SQL Queries and Clauses",
                    "description": "SELECT, WHERE, GROUP BY, HAVING, and ORDER BY clauses.",
                    "questions": [
                        {
                            "text": "Which SQL clause is used to filter records after an aggregate `GROUP BY` operation?",
                            "a": "WHERE",
                            "b": "HAVING",
                            "c": "ORDER BY",
                            "d": "FILTER",
                            "ans": "B",
                            "exp": "`WHERE` filters individual rows before grouping; `HAVING` filters aggregated groups."
                        },
                        {
                            "text": "Which SQL command is used to remove all records from a table without removing the table structure?",
                            "a": "DROP",
                            "b": "DELETE",
                            "c": "TRUNCATE",
                            "d": "REMOVE",
                            "ans": "C",
                            "exp": "`TRUNCATE` removes all rows quickly while retaining table structure and column definitions."
                        }
                    ]
                }
            ]
        }
    ]

    for subj in subjects_data:
        cursor.execute("SELECT id FROM subjects WHERE name = ?", (subj["name"],))
        subject_row = cursor.fetchone()
        if not subject_row:
            cursor.execute("INSERT INTO subjects (name, description) VALUES (?, ?)", (subj["name"], subj["description"]))
            subject_id = cursor.lastrowid
            print(f"Subject seeded: {subj['name']}")
        else:
            subject_id = subject_row["id"]

        for top in subj["topics"]:
            cursor.execute("SELECT id FROM topics WHERE subject_id = ? AND name = ?", (subject_id, top["name"]))
            topic_row = cursor.fetchone()
            if not topic_row:
                cursor.execute("INSERT INTO topics (subject_id, name, description) VALUES (?, ?, ?)", (subject_id, top["name"], top["description"]))
                topic_id = cursor.lastrowid
                print(f"  Topic seeded: {top['name']}")
            else:
                topic_id = topic_row["id"]

            for q in top.get("questions", []):
                cursor.execute("SELECT id FROM questions WHERE topic_id = ? AND question_text = ?", (topic_id, q["text"]))
                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO questions (topic_id, question_text, option_a, option_b, option_c, option_d, correct_answer, explanation)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (topic_id, q["text"], q["a"], q["b"], q["c"], q["d"], q["ans"], q["exp"]))

    conn.commit()
    conn.close()
    print("Database seeding completed successfully.")


if __name__ == '__main__':
    print("Initializing Database...")
    init_db()
    print("Seeding demonstration data...")
    seed_sample_data()
    print("Database ready!")
