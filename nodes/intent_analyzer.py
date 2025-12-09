from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from config.llm import llm
from schemas.state import AgentState
from schemas.intent import UserIntent
from datetime import datetime
from prompts.intent_analyzer_prompt import INTENT_ANALYZER_PROMPT

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", INTENT_ANALYZER_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ]
)

def intent_analyzer_node(state: AgentState):
    """
    Analyzes the user's intent and updates the `user_intent` state.
    """
    now = datetime.now().strftime("%Y-%m-%d")
    formatted_prompt = prompt.partial(current_time=now)
    
    # Use structured output to force the UserIntent schema
    chain = formatted_prompt | llm.with_structured_output(UserIntent)
    
    result = chain.invoke(state)
    
    print(f"DEBUG [IntentAnalyzer] Extracted Intent: {result}")
    
    return {"user_intent": result}