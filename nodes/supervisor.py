
from typing import Literal
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field
from config.llm import llm
from schemas.state import AgentState
from prompts.supervisor_prompt import SUPERVISOR_SYSTEM_PROMPT

# Define the routing options
options = ["CampaignAgent", "PerformanceAgent", "FINISH"]

class RouteSchema(BaseModel):
    """The next role to act."""
    next: Literal["CampaignAgent", "PerformanceAgent", "FINISH"] = Field(
        ..., description="The next agent to act or FINISH"
    )
    instructions: str = Field(
        ..., description="Specific instructions for the selected agent."
    )

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SUPERVISOR_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
        (
            "system",
            "Given the conversation above, who should act next? "
            "Or should we FINISH? Select one of: {options}",
        ),
    ]
).partial(options=str(options))

def supervisor_node(state: AgentState):
    """
    The Supervisor node that decides which agent to call next.
    """
    # Loop Prevention Logic
    # ... (Keep existing logic) ...
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        
        # Helper to safely get attributes whether it's a dict or object
        if isinstance(last_msg, dict):
            msg_type = last_msg.get("type")
            tool_calls = last_msg.get("tool_calls")
            content = last_msg.get("content", "")
        else:
            msg_type = getattr(last_msg, "type", "")
            tool_calls = getattr(last_msg, "tool_calls", [])
            content = getattr(last_msg, "content", "")

        # If the last message is from an AI (Worker) and is not a tool call request (it's a result),
        # we act as if the worker has reported back.
        if msg_type == 'ai' and not tool_calls:
             print(f"DEBUG [Supervisor] Last message was from Worker: {content[:50]}...")
             # Inject a temporary system hint to break the loop
             # We do this by appending a system message to the context passed to invoke
             # Note: This doesn't change the persistent state, only the prompt context.
             messages = list(messages) + [
                 {"role": "system", "content": "The previous agent has responded. If this response is a question for the user (clarification) or a final result, choose FINISH to return control to the user. Do NOT call the same agent again immediately."}
             ]
    
    # Create the chain using with_structured_output
    supervisor_chain = (
        prompt
        | llm.with_structured_output(RouteSchema)
    )
    
    # Pass the potentially modified messages list
    invoke_state = state.copy()
    if messages != state["messages"]:
        invoke_state["messages"] = messages
    
    # Inject user_intent into prompt context
    user_intent = state.get("user_intent")
    if user_intent:
        # Pydantic V2 requires model_dump_json instead of json(indent=2)
        invoke_state["user_intent_context"] = f"User Intent Analysis:\n{user_intent.model_dump_json(indent=2)}"
    else:
        invoke_state["user_intent_context"] = "User Intent: Not available."

    result = supervisor_chain.invoke(invoke_state)
    
    print(f"DEBUG [Supervisor] Decision: {result.next} | Instructions: {result.instructions}") # Debug log
    
    # result is now a Pydantic object (RouteSchema), convert to dict for state update
    return {
        "next": result.next,
        "supervisor_instructions": result.instructions
    }
