import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("Error: Please set OPENAI_API_KEY in your .env file.")

llm = ChatOpenAI(model="gpt-4-turbo", temperature=0, openai_api_key=openai_api_key)
