"""
AI Student Hub — AI Study Assistant Module
Integrates Large Language Model (LLM) APIs (Google Gemini / OpenAI)
to provide personalized explanations, weak topic diagnostics, and study advice.
Includes a graceful offline fallback if API keys are absent or internet is down.
"""

import os
import requests
from dotenv import load_dotenv


def query_llm_api(prompt_text, system_instruction=None):
    """
    Dispatches prompt to Google Gemini or OpenAI REST API.
    Dynamically loads keys from .env on each invocation.
    Returns (response_text, provider_name) or (None, error_str).
    """
    # Always refresh environment variables from .env
    load_dotenv(override=True)
    gemini_key = os.getenv('GEMINI_API_KEY', '').strip()
    openai_key = os.getenv('OPENAI_API_KEY', '').strip()

    # 1. Try Google Gemini API if key is present
    if gemini_key and gemini_key != 'your_gemini_api_key_here':
        # Models tested and verified for Gemini v1beta API
        gemini_models = ['gemini-flash-lite-latest', 'gemini-2.5-flash-lite', 'gemini-flash-latest']
        for model in gemini_models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
                combined_prompt = (f"System Context: {system_instruction}\n\n" if system_instruction else "") + prompt_text
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {"text": combined_prompt}
                            ]
                        }
                    ]
                }
                resp = requests.post(url, json=payload, timeout=12)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and "text" in parts[0]:
                            display_name = f"Google Gemini ({model})"
                            return parts[0]["text"].strip(), display_name
            except Exception:
                continue

    # 2. Try OpenAI API if key is configured
    if openai_key and openai_key != 'your_openai_api_key_here':
        try:
            url = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            }
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt_text})

            payload = {
                "model": "gpt-4o-mini",
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 500
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                return text.strip(), "OpenAI GPT-4o Mini"
        except Exception:
            pass

    return None, "Offline Academic Rule Engine"


def generate_ai_attempt_analysis(student_name, subject_name, topic_name, score, total_questions, percentage, incorrect_items):
    """
    Generates intelligent educational feedback on a completed quiz attempt.
    Explains mistakes and creates a personalized 3-step action roadmap.
    """
    system_instruction = (
        "You are an encouraging, expert Computer Science tutor for undergraduate BCA students. "
        "Keep advice concise, friendly, and practical. Explain concepts in clear, easy-to-understand English with helpful examples."
    )

    incorrect_summary = ""
    for idx, raw_item in enumerate(incorrect_items[:4], 1):
        item = dict(raw_item) if hasattr(raw_item, 'keys') else raw_item
        incorrect_summary += (
            f"\n- Question {idx}: {item.get('question_text', 'N/A')}\n"
            f"  Student selected: Option {item.get('selected_answer', 'None')}\n"
            f"  Correct Answer: Option {item.get('correct_answer', 'N/A')}\n"
            f"  Core Concept: {item.get('explanation', 'N/A')}\n"
        )

    prompt = f"""
Student: {student_name}
Subject: {subject_name}
Topic: {topic_name}
Result: {score}/{total_questions} ({percentage}%)

Mistakes Summary:
{incorrect_summary if incorrect_summary else "Student answered all attempted questions correctly!"}

Please provide:
1. Conceptual Diagnosis: Why these mistakes happen in simple words.
2. 3-Step Study Plan: Immediate practical revision actions.
3. Quick Memory Tip to remember the key concept.
"""

    llm_output, provider = query_llm_api(prompt, system_instruction)

    if llm_output:
        return {
            "advice": llm_output,
            "provider": provider,
            "is_live_ai": True
        }

    # Deterministic Academic Offline Fallback (Guarantees college demo never fails)
    if percentage >= 80:
        diagnosis = f"Superb performance by {student_name} in {topic_name}! You have demonstrated firm conceptual command."
        steps = [
            "Review the edge cases in advanced reference documentation.",
            "Solve practical coding or schema implementation problems related to this topic.",
            "Move on to subsequent syllabus topics or higher-difficulty quizzes."
        ]
        tip = "Consistent hands-on code execution reinforces theoretical recall."
    elif percentage >= 60:
        diagnosis = f"Good effort in {topic_name}, but a few conceptual nuances were missed. Reviewing the provided explanations will solidify your grasp."
        steps = [
            "Carefully re-read the explanation notes for any missed questions below.",
            "Write down short 2-line definitions and examples for the mistaken concepts in your notebook.",
            "Retake this quiz in 24 hours to reinforce memory consolidation."
        ]
        tip = "Pay close attention to keyword operators and return types."
    else:
        diagnosis = f"Critical focus required in {topic_name}. The current score of {percentage}% indicates foundational gaps that need attention."
        steps = [
            "Re-read the lecture notes and official textbook chapter for this specific topic.",
            "Practice small, isolated code examples on your machine.",
            "Retake this quiz until you comfortably achieve an 80%+ score."
        ]
        tip = "Break down complex problems into step-by-step logic before selecting an answer."

    offline_text = (
        f"### Conceptual Diagnosis\n{diagnosis}\n\n"
        f"### Recommended 3-Step Study Plan\n"
        f"1. **Step 1:** {steps[0]}\n"
        f"2. **Step 2:** {steps[1]}\n"
        f"3. **Step 3:** {steps[2]}\n\n"
        f"### Academic Tip\n{tip}"
    )

    return {
        "advice": offline_text,
        "provider": "AI Student Hub Smart Assistant (Offline Mode)",
        "is_live_ai": False
    }


def ask_ai_concept_tutor(user_question, topic_name=None):
    """
    Allows a student to ask any conceptual question to the AI Study Assistant.
    """
    system_instruction = (
        "You are the AI Study Assistant for AI Student Hub (BCA Curriculum). "
        "Explain programming and CS concepts in simple, intuitive terms with small code snippets where helpful."
    )

    context = f"Topic Context: {topic_name}\n" if topic_name else ""
    prompt = f"{context}Student Question: {user_question}\n\nExplain clearly with: 1) Definition, 2) Simple Real-World Example, 3) Key Takeaway."

    llm_output, provider = query_llm_api(prompt, system_instruction)

    if llm_output:
        return {
            "answer": llm_output,
            "provider": provider,
            "is_live_ai": True
        }

    # Clean offline fallback answer for common CS queries
    offline_answer = (
        f"**Question:** {user_question}\n\n"
        f"**AI Tutor Note (Offline):**\n"
        f"To get live AI responses from Gemini, set your `GEMINI_API_KEY` in the `.env` file.\n\n"
        f"**Core Study Rule:** When learning computer science concepts, always practice active coding: "
        f"write the code, run it, observe the output, and experiment with edge conditions."
    )
    return {
        "answer": offline_answer,
        "provider": "AI Student Hub Smart Assistant (Offline Mode)",
        "is_live_ai": False
    }
