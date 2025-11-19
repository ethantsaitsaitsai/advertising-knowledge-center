from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import AIMessage
from schemas.state import AgentState
from config.llm import llm
from typing import Dict, Any, List

# Define the prompt for asking for clarification
ask_for_clarification_prompt_template = PromptTemplate.from_template(
    """
# ROLE
You are a friendly database assistant. Your current task is to get clarification from the user to ensure the database query is accurate.

# CONTEXT
The user's request is either missing some crucial information or contains ambiguous terms.
- The user's original ambiguous term was: '{ambiguous_term}'
- We have found a list of potential candidates from the database: {candidate_values}
- We are also missing the following information: {missing_slots}

# INSTRUCTIONS
1.  **Be Clear and Direct**: Your goal is to get a precise answer from the user.
2.  **Handle Candidates**: If there is a list of `candidate_values`, present them clearly to the user. Ask them to select the ones they want to include. You can number them for easy selection.
3.  **Handle Missing Info**: If there is `missing_slots`, ask the user to provide the missing information.
4.  **Combine if Necessary**: If both situations occur, combine the questions into a single, polite message.
5.  **Example (Candidates only)**: "我找到了幾個與「{ambiguous_term}」相關的項目，請確認您需要哪幾個？\n1. 候選一\n2. 候選二\n您可以回覆編號 (例如: 1, 2)，或告訴我「全部」或「排除 X」。"
6.  **Example (Missing Info only)**: "為了提供更精確的數據，請問您想查詢的 {missing_slots} 是？"
7.  **Example (Combined)**: "好的，關於「{ambiguous_term}」，我找到了幾個相關項目，請確認您需要哪幾個？\n1. 候選一\n2. 候選二\n另外，也想請問您想查詢的 {missing_slots} 是？"

Based on the context, generate the most appropriate question for the user.
"""
)

def get_ask_for_clarification_chain() -> Runnable:
    """
    Get the chain for asking for clarification.
    """
    return ask_for_clarification_prompt_template | llm | StrOutputParser()

def ask_for_clarification_node(state: AgentState) -> Dict[str, Any]:
    """
    When the user's query is incomplete or ambiguous, this node generates follow-up questions.
    If there are candidate values, it asks the user to confirm them.
    """
    ask_for_clarification_chain = get_ask_for_clarification_chain()
    
    missing_slots = state.get("missing_slots", [])
    ambiguous_terms = state.get("ambiguous_terms", [])
    candidate_values = state.get("candidate_values", [])
    
    # If there are candidates, we prioritize asking for entity resolution
    if candidate_values:
        ambiguous_term = ambiguous_terms[0] if ambiguous_terms else ""
        response = ask_for_clarification_chain.invoke({
            "missing_slots": ", ".join(missing_slots),
            "ambiguous_term": ambiguous_term,
            "candidate_values": "\n".join([f"{i+1}. {c}" for i, c in enumerate(candidate_values)]),
        })
    # If no candidates, but missing info, ask for the missing info
    elif missing_slots:
        response = f"為了提供準確的數據，請問您想查詢的『{', '.join(missing_slots)}』是？（例如：2024年全年度、上個月、或是具體日期）"
    else:
        # This case should ideally not be reached if the router is configured correctly
        response = "我需要更多資訊，但無法確定要問什麼。可以請您提供更多細節嗎？"

    
    # Return the generated message and set the flag to expect clarification response
    return {
        "messages": [AIMessage(content=response)],
        "expecting_user_clarification": True,
    }
