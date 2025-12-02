import os
from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

# --- OpenAI Configuration (Commented Out) ---
# openai_api_key = os.getenv("OPENAI_API_KEY")
# if not openai_api_key:
#     raise ValueError("Error: Please set OPENAI_API_KEY in your .env file.")
# llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=openai_api_key)

# --- Google Gemini Configuration ---
gemini_api_key = os.getenv("GEMINI_API_KEY")
if not gemini_api_key:
    raise ValueError("Error: Please set GEMINI_API_KEY in your .env file.")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",
    temperature=0,
    google_api_key=gemini_api_key,
    convert_system_message_to_human=True
)