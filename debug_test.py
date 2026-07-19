"""
Standalone Gemini API key test - isolates whether the key itself works,
independent of the rest of TripCraft's agent stack.

Run from inside the tripcraft folder with your .env filled in:
    python debug_gemini.py
"""
from dotenv import load_dotenv
load_dotenv()

import os

key = os.getenv("GEMINI_API_KEY", "")
print("GEMINI_API_KEY (masked):", (key[:6] + "...") if key else "EMPTY/NOT SET")
print()

if not key:
    print("No key found in .env - nothing to test. Fill in GEMINI_API_KEY first.")
else:
    try:
        import google.generativeai as genai
        genai.configure(api_key=key)

        print("Listing available models (tests auth without spending much quota)...")
        models = list(genai.list_models())
        print(f"SUCCESS - key is valid, found {len(models)} available models.")
        print()

        print("Testing a real generate_content call...")
        model = genai.GenerativeModel("gemini-3.5-flash")
        resp = model.generate_content("Say 'hello' in one word.")
        print("SUCCESS - response:", resp.text.strip())

    except Exception as e:
        print("FAILED:", e)
        print()
        print("If you see ACCOUNT_STATE_INVALID or similar, the key's underlying")
        print("Google Cloud service account is disabled/deleted. Fix: go to")
        print("https://aistudio.google.com/apikey, delete this key, generate a")
        print("brand new one (ideally confirm you're signed into the Google")
        print("account you intend to use), and paste the NEW value into .env.")