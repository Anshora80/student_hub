"""
AI Student Hub — RAG Engine (Retrieval-Augmented Generation & Dynamic Quiz System)
==================================================================================
Handles:
1. Secure PDF text extraction & contextual chunking with page tracking.
2. Vector embeddings generation (Gemini embedding-001) with hybrid semantic fallback.
3. Precise question answering (Chat with Document) grounded exclusively in syllabus text.
4. Dynamic Top-10 MCQ quiz generation with deduplication for "Next 10 Questions".
5. Post-quiz weak area & learning pattern diagnostic analysis.
"""

import os
import math
import json
import hashlib
import re
import requests
from dotenv import load_dotenv
from pypdf import PdfReader
from database import get_db_connection
from ai_assistant import query_llm_api


def extract_text_and_chunks_from_pdf(pdf_path, chunk_size=800, chunk_overlap=150):
    """
    Extracts text from PDF page-by-page and segments it into overlapping chunks.
    Preserves page numbers for source citation.
    Returns (total_pages, chunks_list).
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at: {pdf_path}")

    reader = PdfReader(pdf_path)

    # Handle standard PDF encryption (AES / RC4)
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            try:
                reader.decrypt(b"")
            except Exception as dec_err:
                raise ValueError("This PDF is password-protected. Please upload an unprotected PDF file.")

    total_pages = len(reader.pages)
    if total_pages == 0:
        raise ValueError("The uploaded PDF has 0 pages.")

    raw_chunks = []
    chunk_index = 0

    for page_idx, page in enumerate(reader.pages):
        page_num = page_idx + 1
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        # Clean up whitespace and excessive blank lines
        clean_text = re.sub(r'\s+', ' ', page_text).strip()
        if not clean_text:
            continue

        # Segment page text into overlapping windows
        start = 0
        text_len = len(clean_text)
        while start < text_len:
            end = min(start + chunk_size, text_len)
            chunk_slice = clean_text[start:end].strip()
            if len(chunk_slice) >= 60:  # Ignore tiny noise fragments
                raw_chunks.append({
                    "chunk_index": chunk_index,
                    "page_number": page_num,
                    "chunk_text": chunk_slice
                })
                chunk_index += 1
            if end >= text_len:
                break
            start += (chunk_size - chunk_overlap)

    if not raw_chunks:
        raise ValueError("Could not extract readable text from this PDF. Please ensure it contains selectable text, not scanned images.")

    return total_pages, raw_chunks


def get_gemini_embedding(text):
    """
    Generates semantic vector embedding using Gemini embedding API.
    Returns list of floats or None if API quota/network is unavailable.
    """
    load_dotenv(override=True)
    gemini_key = os.getenv('GEMINI_API_KEY', '').strip()
    if not gemini_key or gemini_key =='GEMINI_API_KEY':
        return None

    # Supported embedding models
    models = ['gemini-embedding-001', 'gemini-embedding-2']
    for model_name in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:embedContent?key={gemini_key}"
            payload = {
                "model": f"models/{model_name}",
                "content": {
                    "parts": [{"text": text[:2000]}]  # Cap length for safety
                }
            }
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                embedding = data.get("embedding", {}).get("values")
                if embedding:
                    return embedding
        except Exception:
            continue
    return None


def cosine_similarity(v1, v2):
    """Computes cosine similarity between two numeric vectors in pure Python."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def term_overlap_score(query, text):
    """Fallback lexical similarity when vector embeddings are unavailable offline."""
    query_words = set(re.findall(r'\b\w{3,}\b', query.lower()))
    if not query_words:
        return 0.0
    text_words = set(re.findall(r'\b\w{3,}\b', text.lower()))
    overlap = len(query_words.intersection(text_words))
    return overlap / len(query_words)


def find_top_relevant_chunks(document_id, query_text, top_k=4):
    """
    Retrieves the most semantically relevant chunks for a question.
    Uses hybrid search: Vector Cosine Similarity if embeddings exist,
    backed by lexical token overlap.
    """
    conn = get_db_connection()
    chunks = conn.execute("""
        SELECT id, chunk_index, page_number, chunk_text, embedding_json
        FROM document_chunks
        WHERE document_id = ?
        ORDER BY chunk_index ASC
    """, (document_id,)).fetchall()
    conn.close()

    if not chunks:
        return []

    query_embedding = get_gemini_embedding(query_text)
    scored_chunks = []

    for c in chunks:
        score = 0.0
        # If both chunk embedding and query embedding are available, calculate cosine similarity
        if query_embedding and c['embedding_json']:
            try:
                chunk_vec = json.loads(c['embedding_json'])
                score = cosine_similarity(query_embedding, chunk_vec)
            except Exception:
                score = term_overlap_score(query_text, c['chunk_text'])
        else:
            score = term_overlap_score(query_text, c['chunk_text'])

        scored_chunks.append({
            "page_number": c['page_number'],
            "chunk_text": c['chunk_text'],
            "score": score
        })

    # Sort descending by score
    scored_chunks.sort(key=lambda x: x['score'], reverse=True)
    return scored_chunks[:top_k]


def answer_question_from_document(document_id, doc_title, question_text):
    """
    Answers a student's question grounded strictly in their uploaded PDF content.
    Returns dict with answer, provider, and source citations.
    """
    relevant_chunks = find_top_relevant_chunks(document_id, question_text, top_k=4)

    if not relevant_chunks:
        return {
            "answer": "No content found in this document to answer your question.",
            "sources": [],
            "provider": "Document Search"
        }

    # Assemble context with page citations
    context_blocks = []
    sources = []
    for c in relevant_chunks:
        context_blocks.append(f"[Excerpt from Page {c['page_number']}]:\n{c['chunk_text']}")
        sources.append({
            "page": c['page_number'],
            "snippet": c['chunk_text'][:160] + "..."
        })

    combined_context = "\n\n".join(context_blocks)

    system_instruction = (
        f"You are an expert academic tutor for a student studying their uploaded syllabus or course notes: '{doc_title}'. "
        "Answer the student's question PRECISELY and CLEARLY based on the provided document excerpts. "
        "Highlight important terms and concepts. "
        "Cite the specific Page number(s) where the concept was located in your answer. "
        "If the provided excerpts do not mention the answer, explicitly inform the student that it is not covered in their document."
    )

    prompt = f"""DOCUMENT CONTEXT:
{combined_context}

STUDENT QUESTION:
{question_text}

Provide a direct, complete, and precise explanation."""

    answer_text, provider = query_llm_api(prompt, system_instruction)

    if not answer_text:
        # Fallback offline synthesis if LLM is unavailable
        answer_text = (
            f"Here are the most relevant excerpts found in **{doc_title}** regarding your query:\n\n"
            + "\n\n".join([f"• **Page {s['page']}:** {s['snippet']}" for s in sources])
            + "\n\n*(Connect your Gemini API Key in .env for full conversational AI answers)*"
        )
        provider = "AI Student Hub Offline Grounded RAG"

    return {
        "answer": answer_text,
        "sources": sources,
        "provider": provider
    }


def generate_dynamic_quiz_from_document(document_id, user_id, batch_number=1, count=10):
    """
    Generates 10 high-yield Multiple Choice Questions (MCQs) from the uploaded PDF.
    Ensures non-duplication by excluding previously generated question hashes.
    Stores new questions into `document_quizzes`.
    Returns list of saved question records.
    """
    conn = get_db_connection()

    # 1. Fetch document metadata
    doc = conn.execute("SELECT * FROM user_documents WHERE id = ?", (document_id,)).fetchone()
    if not doc:
        conn.close()
        raise ValueError("Document not found.")

    # 2. Fetch existing question hashes to prevent repeats in "Next 10"
    existing_hashes = set(row[0] for row in conn.execute(
        "SELECT question_hash FROM document_quizzes WHERE document_id = ?", (document_id,)
    ).fetchall())

    # 3. Retrieve representative chunks across the document
    chunks = conn.execute("""
        SELECT chunk_text, page_number FROM document_chunks
        WHERE document_id = ?
        ORDER BY chunk_index ASC
    """, (document_id,)).fetchall()

    if not chunks:
        conn.close()
        raise ValueError("No text chunks available in this document to generate quiz.")

    # Evenly sample chunks across document
    total_c = len(chunks)
    step = max(1, total_c // 12)
    sample_text = ""
    for i in range(0, total_c, step):
        sample_text += f"\n[Page {chunks[i]['page_number']} Content]: {chunks[i]['chunk_text'][:400]}\n"
        if len(sample_text) > 6000:
            break

    system_instruction = (
        "You are an academic exam creator for undergraduate/competitive level students. "
        f"Generate exactly {count} unique, high-yield Multiple Choice Questions (MCQs) based on the provided document excerpts. "
        "Each question must test conceptual understanding, key terminology, or principles from the document. "
        "Format output STRICTLY as a valid JSON array of objects without any markdown code fences or conversational text. "
        "Each object must have these exact keys: "
        "'question', 'option_a', 'option_b', 'option_c', 'option_d', 'correct_answer' (must be 'A','B','C', or 'D'), 'explanation'."
    )

    prompt = f"""EXCERPTS FROM DOCUMENT '{doc['title']}':
{sample_text}

GENERATE EXACTLY {count} MULTIPLE CHOICE QUESTIONS.
Batch Number: {batch_number}.
DO NOT repeat basic questions. Focus on core curriculum topics.

JSON Schema:
[
  {{
    "question": "Question statement here",
    "option_a": "Option A text",
    "option_b": "Option B text",
    "option_c": "Option C text",
    "option_d": "Option D text",
    "correct_answer": "A",
    "explanation": "Why this answer is correct according to the document"
  }}
]"""

    response_text, provider = query_llm_api(prompt, system_instruction)

    # Clean JSON output from potential markdown fences
    parsed_questions = []
    if response_text:
        cleaned_json = re.sub(r'^```json\s*', '', response_text.strip())
        cleaned_json = re.sub(r'\s*```$', '', cleaned_json.strip())
        try:
            parsed_questions = json.loads(cleaned_json)
        except Exception:
            # Fallback regex extraction if full JSON parsing failed
            match = re.search(r'\[\s*\{.*\}\s*\]', response_text, re.DOTALL)
            if match:
                try:
                    parsed_questions = json.loads(match.group(0))
                except Exception:
                    pass

    # Fallback default questions if LLM failed or quota exceeded
    if not parsed_questions:
        parsed_questions = [
            {
                "question": f"What is a primary objective or central theme discussed in '{doc['title']}'?",
                "option_a": "Understanding fundamental principles and core curriculum topics",
                "option_b": "Unrelated peripheral case studies",
                "option_c": "Deprecated historical methods",
                "option_d": "None of the above",
                "correct_answer": "A",
                "explanation": "Academic syllabi and lecture notes are structured around core fundamental principles."
            },
            {
                "question": f"According to the syllabus structure in '{doc['title']}', how should concepts be mastered?",
                "option_a": "Rote memorization without application",
                "option_b": "Sequential conceptual progression from basics to advanced applications",
                "option_c": "Skipping foundational prerequisites",
                "option_d": "Only studying past exam questions",
                "correct_answer": "B",
                "explanation": "Higher education frameworks require progressive mastery from foundational to applied concepts."
            }
        ]

    # Insert into database with duplicate prevention
    saved_questions = []
    cursor = conn.cursor()

    for item in parsed_questions:
        q_text = item.get('question', '').strip()
        opt_a = item.get('option_a', '').strip()
        opt_b = item.get('option_b', '').strip()
        opt_c = item.get('option_c', '').strip()
        opt_d = item.get('option_d', '').strip()
        ans = item.get('correct_answer', 'A').strip().upper()
        if ans not in ['A', 'B', 'C', 'D']:
            ans = 'A'
        exp = item.get('explanation', '').strip()

        if not q_text or not opt_a or not opt_b:
            continue

        q_hash = hashlib.sha256(q_text.lower().encode('utf-8')).hexdigest()
        # If question was already generated in a previous batch, skip to guarantee fresh questions!
        if q_hash in existing_hashes:
            continue

        cursor.execute("""
            INSERT INTO document_quizzes (
                document_id, user_id, question_text, option_a, option_b, option_c, option_d,
                correct_answer, explanation, question_hash, batch_number
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (document_id, user_id, q_text, opt_a, opt_b, opt_c, opt_d, ans, exp, q_hash, batch_number))

        existing_hashes.add(q_hash)
        saved_questions.append({
            "id": cursor.lastrowid,
            "question_text": q_text,
            "option_a": opt_a,
            "option_b": opt_b,
            "option_c": opt_c,
            "option_d": opt_d,
            "correct_answer": ans,
            "explanation": exp,
            "batch_number": batch_number
        })

    conn.commit()
    conn.close()
    return saved_questions


def analyze_document_quiz_performance(doc_title, score, total_questions, percentage, incorrect_list):
    """
    Generates intelligent post-quiz diagnostic analysis:
    - Identifies weak areas & conceptual misconceptions.
    - Evaluates learning patterns & cognitive retention.
    - Prescribes a targeted 3-step revision plan.
    """
    mistakes_str = ""
    for idx, item in enumerate(incorrect_list[:5], 1):
        mistakes_str += (
            f"\n- Q{idx}: {item.get('question_text')}\n"
            f"  Your Answer: Option {item.get('selected_answer')}\n"
            f"  Correct Answer: Option {item.get('correct_answer')}\n"
            f"  Concept: {item.get('explanation')}\n"
        )

    system_instruction = (
        "You are a Senior Academic Mentor. Analyze a student's quiz performance on their uploaded syllabus/notes. "
        "Explain their weak areas with empathy, point out conceptual traps, and provide a clear actionable roadmap."
    )

    prompt = f"""DOCUMENT: {doc_title}
STUDENT SCORE: {score} out of {total_questions} ({percentage}%)

MISSED QUESTIONS:
{mistakes_str if mistakes_str else "All questions answered correctly! Perfect mastery."}

PROVIDE:
1. WEAK AREA DIAGNOSIS: Pinpoint specific concepts or topics from the document that caused errors.
2. LEARNING PATTERN & RETENTION INSIGHT: Analyze how the student is approaching these questions.
3. 3-STEP TARGETED REVISION PLAN: Immediate practical steps to review in their notes before taking the next quiz batch.
"""

    analysis_text, provider = query_llm_api(prompt, system_instruction)

    if not analysis_text:
        # High quality offline fallback
        if percentage >= 80:
            analysis_text = (
                f"### 🌟 Mastery Analysis for {doc_title}\n"
                f"You achieved an outstanding score of {percentage}%. You have grasped the fundamental definitions and logic in this syllabus.\n\n"
                "### 📈 Learning Pattern Insight\n"
                "Your retention is high. You understand the core terminology and distinguish between subtle distractors.\n\n"
                "### 🚀 Recommended Next Steps\n"
                "1. Click **'Next 10 Questions'** to test deeper edge cases from your document.\n"
                "2. Try explaining the main concepts in your own words to solidify active recall.\n"
                "3. Review the quick explanations for any questions you hesitated on."
            )
        elif percentage >= 60:
            analysis_text = (
                f"### 🟡 Competent Foundation with Revision Areas for {doc_title}\n"
                f"You scored {percentage}%. You have good baseline knowledge, but specific details or application nuances tripped you up.\n\n"
                "### 🔍 Weak Area Identification\n"
                "Review the questions marked in red below. Pay close attention to definitions, conditions, and core formulas.\n\n"
                "### 🚀 3-Step Action Plan\n"
                "1. Re-read the specific sections of your PDF corresponding to the missed questions.\n"
                "2. Note down 2-line flashcards for the correct explanations shown below.\n"
                "3. Retake this quiz or generate **Next 10 Questions** to reinforce memory consolidation."
            )
        else:
            analysis_text = (
                f"### 🔴 Priority Study Required for {doc_title}\n"
                f"Your current score is {percentage}%. Foundational concepts in this syllabus require focused re-reading.\n\n"
                "### 🔍 Weak Area Identification\n"
                "Several core questions were missed. This typically occurs when studying complex notes quickly without summarizing key takeaways.\n\n"
                "### 🚀 3-Step Action Plan\n"
                "1. Open your PDF notes and read through the highlighted topics before testing again.\n"
                "2. Use the **'Ask AI Tutor / Chat with Document'** feature to clarify any confusing concepts.\n"
                "3. Re-attempt this quiz batch to raise your baseline score above 70%."
            )

    return analysis_text
