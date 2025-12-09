
from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage
from nodes.campaign_agent import create_campaign_agent
from schemas.state import AgentState
import json

# Initialize the agent once
campaign_runnable = create_campaign_agent()

def campaign_node(state: AgentState):
    """
    Executes the Campaign Agent and updates the state with the result.
    """
    messages = list(state["messages"])
    
    # Inject Supervisor Instructions
    instructions = state.get("supervisor_instructions")
    if instructions:
        print(f"DEBUG [CampaignNode] Supervisor Instructions: {instructions}")
        messages.append(SystemMessage(content=f"Supervisor Instructions: {instructions}"))

    # Invoke the agent with just the messages
    # We pass the full history so the agent has context
    result = campaign_runnable.invoke(
        {"messages": messages}
    )
    
    # 1. Handle Message History Update
    last_message = result["messages"][-1]
    
    # Context Window Protection
    MAX_CONTENT_LENGTH = 10000
    if len(last_message.content) > MAX_CONTENT_LENGTH:
        print(f"DEBUG [CampaignNode] Truncating output from {len(last_message.content)} chars.")
        last_message.content = last_message.content[:MAX_CONTENT_LENGTH] + "\n... [Output Truncated for Supervisor] ..."
    
    # 2. Extract Structured Data from Tool Output (for inter-agent communication)
    campaign_data = state.get("campaign_data") # Preserve existing if no new data
    
    # Iterate in reverse to find the latest tool output
    for msg in reversed(result["messages"]):
        if isinstance(msg, ToolMessage) and msg.name == "query_campaign_data":
            try:
                # The tool output is a JSON string
                tool_output = json.loads(msg.content)
                if isinstance(tool_output, dict) and "data" in tool_output:
                    print(f"DEBUG [CampaignNode] Extracted {len(tool_output['data'])} rows of campaign data.")
                    
                    # Debug: Print Generated SQL
                    sqls = tool_output.get("generated_sqls", [])
                    if sqls:
                        print(f"DEBUG [CampaignNode] Generated SQL:\n{sqls[0]}")
                        
                    campaign_data = tool_output # Store the full structure (data + columns)
                    break
            except json.JSONDecodeError:
                print("DEBUG [CampaignNode] Failed to parse tool output JSON.")
    
    return {
        "messages": state["messages"] + [last_message],
        "campaign_data": campaign_data
    }
