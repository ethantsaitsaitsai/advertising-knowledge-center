from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from config.llm import llm
from schemas.state import AgentState
from schemas.intent import UserIntent
from prompts.intent_analyzer_prompt import INTENT_ANALYZER_PROMPT
from tools.search_db import search_ambiguous_term

# Try to import the new create_agent. 
try:
    from langchain.agents import create_agent
    HAS_CREATE_AGENT = True
except ImportError:
    HAS_CREATE_AGENT = False
    from langgraph.prebuilt import ToolNode
    from langgraph.graph import StateGraph, END, START, MessagesState

def intent_analyzer_node(state: AgentState):
    """
    Agentic Intent Analyzer: Can use tools to verify entities before finalizing intent.
    """
    # 1. Prepare Input
    messages = list(state.get("messages", []))
    
    # Inject System Prompt
    now = datetime.now().strftime("%Y-%m-%d")
    prev_intent = state.get("user_intent")
    prev_intent_str = prev_intent.model_dump_json(indent=2) if prev_intent else "None"
    
    system_prompt = INTENT_ANALYZER_PROMPT.format(
        current_time=now,
        prev_intent=prev_intent_str
    ) + "\n\n" + "**重要**: 如果發現實體名稱模糊，請務必呼叫 `search_ambiguous_term` 工具進行驗證！"
    
    tools = [search_ambiguous_term]

    # 2. Run Agent
    if HAS_CREATE_AGENT:
        agent = create_agent(model=llm, tools=tools, system_prompt=system_prompt)
        result = agent.invoke({"messages": messages})
    else:
        llm_with_tools = llm.bind_tools(tools)
        
        def agent_node(state: MessagesState):
            msgs = [SystemMessage(content=system_prompt)] + state["messages"]
            return {"messages": [llm_with_tools.invoke(msgs)]}

        def should_continue(state: MessagesState):
            last_msg = state["messages"][-1]
            if last_msg.tool_calls:
                return "tools"
            return END

        workflow = StateGraph(MessagesState)
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", ToolNode(tools))
        workflow.add_edge(START, "agent")
        workflow.add_conditional_edges("agent", should_continue, ["tools", END])
        workflow.add_edge("tools", "agent")
        
        app = workflow.compile()
        result = app.invoke({"messages": messages})

    # 3. Extract Result
    last_message = result["messages"][-1]
    final_content = last_message.content
    
    # Handle list content (common in Anthropic/Gemini)
    if isinstance(final_content, list):
        text_parts = []
        for item in final_content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
            elif isinstance(item, str):
                text_parts.append(item)
        final_content = "\n".join(text_parts)
    
    print(f"DEBUG [IntentAgent] Final Content: {final_content[:2000]}...")
    
    # 4. Format to JSON (Optimized: Regex First -> LLM Fallback)
    import re
    import json
    
    final_intent = None
    
    # Try Regex extraction
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", final_content, re.DOTALL)
    if json_match:
        try:
            json_str = json_match.group(1)
            data = json.loads(json_str, strict=False)
            final_intent = UserIntent(**data)
            print("DEBUG [IntentAgent] Successfully extracted JSON via Regex.")
        except Exception as e:
            print(f"DEBUG [IntentAgent] Regex extraction failed: {e}")
            
    # Fallback to LLM
    if not final_intent:
        print("DEBUG [IntentAgent] Fallback to LLM extraction.")
        formatter_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a JSON extractor."),
            ("user", "Extract the UserIntent JSON from the following text:\n\n{text}")
        ])
        formatter_chain = formatter_prompt | llm.with_structured_output(UserIntent)
        try:
            final_intent = formatter_chain.invoke({"text": final_content})
        except Exception as e:
            print(f"DEBUG [IntentAgent] Fallback LLM failed: {e}")
            
    # Safety Check: If extraction failed completely
    if final_intent is None:
        print("CRITICAL WARNING [IntentAgent] Failed to extract Intent. Defaulting to Chitchat.")
        # Create a safe default to prevent crash
        final_intent = UserIntent(
            query_level='chitchat',
            entities=[],
            date_range=None,
            needs_performance=False,
            is_ambiguous=False,
            ambiguous_options=[],
            missing_info=[],
            analysis_needs={}
        )
    
    print(f"DEBUG [IntentAgent] Final Structured Intent: {final_intent}")
    
    # --- 5. Clean up for User ---
    # Remove the JSON block from the text so the user only sees the natural language response
    clean_content = re.sub(r"```json\s*\{.*?\}\s*```", "", final_content, flags=re.DOTALL).strip()
    
    # Create a new message with the clean content
    # This replaces the raw multi-part message from the LLM, ensuring consistent display
    response_msg = AIMessage(content=clean_content)
    
    # 6. State Merge (Python Logic)
    if prev_intent:
        print(f"DEBUG [IntentAnalyzer] Merging State. Prev Analysis: {prev_intent.analysis_needs}, Curr Analysis: {final_intent.analysis_needs}")
        
        if not final_intent.entities and prev_intent.entities:
            final_intent.entities = prev_intent.entities
        if not final_intent.date_range and prev_intent.date_range:
            final_intent.date_range = prev_intent.date_range
        if prev_intent.needs_performance:
            final_intent.needs_performance = True
        
        if not final_intent.analysis_needs and prev_intent.analysis_needs:
            print(f"DEBUG [IntentAnalyzer] Inheriting Analysis Needs from previous state.")
            final_intent.analysis_needs = prev_intent.analysis_needs
            
        if final_intent.query_level == 'chitchat' and (final_intent.entities or final_intent.date_range):
            final_intent.query_level = prev_intent.query_level
            
        missing = []
        if final_intent.query_level in ["contract", "strategy", "execution", "audience"]:
            if not final_intent.date_range:
                missing.append("date_range")
        final_intent.missing_info = missing

    # Return the intent AND the clean message
    return {
        "user_intent": final_intent,
        "messages": [response_msg]
    }
