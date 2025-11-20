from langchain_core.messages import AIMessage
from schemas.state import AgentState
from config.llm import llm
from langchain_core.prompts import ChatPromptTemplate

CHITCHAT_PROMPT = """
# 角色
你是一個樂於助人的助理。你的使用者正在與你交談。

# 任務
以友善且對話式的語氣回應使用者的訊息。一律以繁體中文回應。

使用者訊息: {user_message}
你的回應:
"""


def chitchat_node(state: AgentState):
    """
    Handles greeting and other non-data-query intents by using an LLM to generate a friendly response.
    """
    last_user_message = ""
    if state['messages'] and isinstance(state['messages'][-1], AIMessage):
        # This case might happen if there's an error and we loop back.
        # To be safe, let's find the last human message.
        for msg in reversed(state['messages']):
            if not isinstance(msg, AIMessage):
                last_user_message = msg.content
                break
    elif state['messages']:
        last_user_message = state['messages'][-1].content
        # Should not happen, but as a fallback
        last_user_message = "Hello"

    prompt = ChatPromptTemplate.from_template(CHITCHAT_PROMPT)
    chain = prompt | llm
    response = chain.invoke({"user_message": last_user_message})
    return {"messages": [AIMessage(content=response.content)]}
