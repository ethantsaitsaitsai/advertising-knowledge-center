from datetime import datetime
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from config.llm import llm
from config.registry import config
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

    # Check if this is a clarification response (user responding to a disambiguation question)
    clarification_pending = state.get("clarification_pending", False)
    if clarification_pending and messages:
        # Find the most recent HumanMessage (user's clarification response)
        user_response = None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                user_response = msg.content
                break

        if user_response:
            print(f"DEBUG [IntentAnalyzer] Clarification response detected: {user_response}")
            print(f"DEBUG [IntentAnalyzer] User clarifying with: {user_response}")
            # 【CRITICAL】User has responded to clarification question
            # They likely provided entity/date, so we should resolve ambiguity
            # Don't override yet - let LLM analyze the response first
            # But flag that this is clarification context so LLM knows
            pass
    
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
        
        # --- Prepare tool_kwargs for search_ambiguous_term ---
        tool_kwargs = {}
        last_user_message_content = ""
        if messages:
            for msg in reversed(messages):
                if isinstance(msg, HumanMessage):
                    last_user_message_content = msg.content
                    break
        
        # Determine search scope based on keywords in the last user message
        search_scope = []
        if "代理商" in last_user_message_content or "agency" in last_user_message_content.lower():
            search_scope.append("agencies")
        if "品牌" in last_user_message_content or "brand" in last_user_message_content.lower():
            search_scope.append("brands")
        if "廣告主" in last_user_message_content or "advertiser" in last_user_message_content.lower():
            search_scope.append("advertisers")
        if "活動名稱" in last_user_message_content or "活動" in last_user_message_content.lower():
            search_scope.append("campaign_names")
            
        if search_scope:
            tool_kwargs = {"search_ambiguous_term": {"scope": search_scope}}
            print(f"DEBUG [IntentAnalyzer] Dynamic search scope set: {search_scope}")

        result = agent.invoke({"messages": messages}, tool_kwargs=tool_kwargs)
    else:
        llm_with_tools = llm.bind_tools(tools)
        
        def agent_node(state: MessagesState):
            msgs = [SystemMessage(content=system_prompt)] + state["messages"]
            # Dynamically determine tool_kwargs if possible for non-create_agent flow
            # This part is more complex for direct LangGraph bind_tools without create_agent
            # For simplicity, assuming LLM will handle scope if prompt is good, or needs more advanced integration
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
            # Clean up malformed JSON: remove literal newlines within string values
            # Replace newlines that appear between quotes with spaces
            json_str = re.sub(r'"\s*\n\s*', '" ', json_str)
            json_str = re.sub(r'\n\s*"', ' "', json_str)
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

    # --- Heuristic Recovery (Salvage Analysis Needs) ---
    # If JSON parsing failed to get analysis_needs, try regex scanning for patterns
    if not final_intent.analysis_needs:
        try:
            print("DEBUG [IntentAgent] Attempting Heuristic Recovery for Analysis Needs...")
            
            # Use finditer to catch ALL occurrences (handling duplicate keys)
            dims_matches = re.finditer(r'"dimensions":\s*\[([^\]]*)\]', final_content, re.DOTALL)
            metrics_matches = re.finditer(r'"metrics":\s*\[([^\]]*)\]', final_content, re.DOTALL)
            
            recovered_needs = {}
            
            # Whitelist for sanitization - loaded from config
            VALID_DIMENSIONS = config.get_valid_dimensions()
            VALID_METRICS = config.get_valid_metrics()
            
            # Process all Dimensions blocks
            clean_dims = []
            for match in dims_matches:
                raw_dims = re.findall(r'"([^"]+)"', match.group(1))
                for d in raw_dims:
                    d_lower = d.lower()
                    if d_lower in VALID_DIMENSIONS:
                        clean_dims.append(VALID_DIMENSIONS[d_lower])
                    else:
                        for valid_k, valid_v in VALID_DIMENSIONS.items():
                            if d_lower in valid_k or valid_k in d_lower:
                                clean_dims.append(valid_v)
                                break
            if clean_dims: recovered_needs["dimensions"] = list(set(clean_dims))
            
            # Process all Metrics blocks
            clean_metrics = []
            for match in metrics_matches:
                raw_metrics = re.findall(r'"([^"]+)"', match.group(1))
                for m in raw_metrics:
                    if any(vm in m.lower() for vm in VALID_METRICS):
                        clean_metrics.append(m)
            if clean_metrics: recovered_needs["metrics"] = list(set(clean_metrics))
                
            if recovered_needs:
                print(f"DEBUG [IntentAgent] Heuristic Recovery for Analysis Needs: {recovered_needs}")
                final_intent.analysis_needs = recovered_needs
        except Exception as e:
            print(f"DEBUG [IntentAgent] Heuristic Recovery failed: {e}")

    # --- Last Resort: Keyword Scan on User Input ---
    if not final_intent.analysis_needs and messages:
        last_msg = messages[-1]
        if hasattr(last_msg, "content"):
            text = last_msg.content
            print(f"DEBUG [IntentAgent] Scanning User Input for Keywords: {text[:50]}...")
            
            needs = {"dimensions": [], "metrics": []}
            
            # Dimensions
            if "廣告主" in text or "Advertiser" in text: needs["dimensions"].append("Advertiser")
            if "代理商" in text or "Agency" in text: needs["dimensions"].append("Agency")
            if "活動" in text or "Campaign" in text: needs["dimensions"].append("Campaign_Name")
            if "格式" in text or "Format" in text: needs["dimensions"].append("Ad_Format")
            if "受眾" in text or "Segment" in text: needs["dimensions"].append("Segment_Category")
            
            # Metrics (Basic)
            if "預算" in text or "金額" in text or "Budget" in text: needs["metrics"].append("Budget_Sum")
            if "成效" in text or "CTR" in text: needs["metrics"].extend(["CTR", "VTR", "ER"])
            
            if needs["dimensions"] or needs["metrics"]:
                print(f"DEBUG [IntentAgent] Keyword Scan found: {needs}")
                final_intent.analysis_needs = needs

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

    # --- Auto-detect needs_performance based on requested metrics ---
    # ClickHouse-only metrics that require performance data
    CLICKHOUSE_METRICS = {"CTR", "VTR", "ER", "Click", "Impression", "View3s", "Q100"}
    if final_intent.analysis_needs:
        requested_metrics = final_intent.analysis_needs.get("metrics", [])
        if any(metric in CLICKHOUSE_METRICS for metric in requested_metrics):
            if not final_intent.needs_performance:
                print(f"DEBUG [IntentAnalyzer] Auto-detecting needs_performance=True (found ClickHouse metrics: {requested_metrics})")
                final_intent.needs_performance = True

    # 【CRITICAL FIX】 If user has provided BOTH entities and date_range,
    # clear is_ambiguous flag - ambiguity is resolved by user clarification!
    # This prevents Supervisor from asking for more clarification
    if clarification_pending and final_intent.entities and final_intent.date_range:
        print(f"DEBUG [IntentAnalyzer] User provided entities + date_range during clarification.")
        print(f"DEBUG [IntentAnalyzer] CLEARING is_ambiguous: True → False (ambiguity resolved by user)")
        final_intent.is_ambiguous = False

    # Return the intent AND the clean message
    return {
        "user_intent": final_intent,
        "messages": [response_msg]
    }
