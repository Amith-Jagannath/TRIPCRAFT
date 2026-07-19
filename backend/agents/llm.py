"""
Thin LLM wrapper so the rest of the codebase never imports a specific
provider's SDK directly. Swap providers by changing LLM_PROVIDER in .env -
no other file needs to change. Defaults to Gemini (free tier).
"""
from __future__ import annotations
import os

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()


def _call_gemini(prompt: str, max_tokens: int = 500) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel("gemini-3.5-flash")
    resp = model.generate_content(prompt, generation_config={"max_output_tokens": max_tokens})
    return resp.text.strip()


def _call_claude(prompt: str, max_tokens: int = 500) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text.strip()


def _call_cohere(prompt: str, max_tokens: int = 500) -> str:
    import cohere
    client = cohere.Client(os.getenv("COHERE_API_KEY"))
    resp = client.chat(message=prompt, max_tokens=max_tokens)
    return resp.text.strip()


def call_llm(prompt: str, max_tokens: int = 500) -> str:
    try:
        if LLM_PROVIDER == "gemini":
            return _call_gemini(prompt, max_tokens)
        elif LLM_PROVIDER == "claude":
            return _call_claude(prompt, max_tokens)
        elif LLM_PROVIDER == "cohere":
            return _call_cohere(prompt, max_tokens)
        else:
            raise ValueError(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}")
    except Exception as e:
        # Never let a flaky LLM call crash the whole agent graph - degrade
        # gracefully with a visible placeholder instead.
        return f"[LLM call failed: {e}]"
