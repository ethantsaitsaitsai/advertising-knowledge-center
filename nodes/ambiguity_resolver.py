from langchain_core.messages import AIMessage, HumanMessage
from schemas.state import GraphState
from tools.tool_registry import all_tools


def ambiguity_resolver_node(state: GraphState) -> GraphState:
    """
    Resolves ambiguous terms by either processing a user's clarification
    or by finding and asking for clarification on a new ambiguous term.
    """
    print("---AMBIGUITY RESOLVER---")
    messages = state["messages"]
    pending_clarification = state.get("pending_clarification") or {}
    term_clarifications = state.get("term_clarifications") or []

    # Step 1: Check if we are in the middle of a clarification
    if pending_clarification and isinstance(messages[-1], HumanMessage):
        user_response = messages[-1].content.strip()
        options = pending_clarification.get("options", [])
        term_to_clarify = pending_clarification.get("term")
        
        matched_option = None
        # Try to match by number
        if user_response.isdigit():
            try:
                choice_index = int(user_response) - 1
                if 0 <= choice_index < len(options):
                    matched_option = options[choice_index]
            except (ValueError, IndexError):
                pass
        
        # If not matched by number, try to match by value
        if not matched_option:
            for option in options:
                if user_response.lower() in option['value'].lower():
                    matched_option = option
                    break
        
        if matched_option:
            # User provided a valid clarification
            term_clarifications.append({
                "term": term_to_clarify,
                "column": matched_option["column"],
                "value": matched_option["value"],
            })
            # Clear the pending state
            pending_clarification = {}
            print(f"Clarified '{term_to_clarify}' to '{matched_option['value']}' in column '{matched_option['column']}'")
        else:
            # User response was not helpful, ask again
            options_str = ", ".join([f"{i+1}. {opt['column']}: {opt['value']}" for i, opt in enumerate(options)])
            messages.append(AIMessage(content=f"抱歉，無法理解您的選擇。請從以下選項中選擇一個：{options_str}"))
            return {
                "messages": messages,
                "pending_clarification": pending_clarification,
                "term_clarifications": term_clarifications,
                "current_stage": "human_in_the_loop",
            }

    # Step 2: Find the next ambiguous term to process
    analysis_result = state["analysis_result"]
    all_ambiguous_terms = analysis_result.get("ambiguous_terms", [])
    clarified_terms = [c["term"] for c in term_clarifications]
    
    next_ambiguous_term = None
    for term in all_ambiguous_terms:
        if term not in clarified_terms:
            next_ambiguous_term = term
            break

    if not next_ambiguous_term:
        # All terms are clarified, we are done here.
        print("All ambiguous terms have been clarified.")
        return {
            "term_clarifications": term_clarifications,
            "pending_clarification": {}, # Ensure pending is cleared
            "current_stage": "ambiguity_resolver",
        }

    # Step 3: Process the next ambiguous term
    term = next_ambiguous_term
    
    # Handle date terms (this is a simplified, non-interactive clarification)
    date_map = {
        "昨天": "DATE(`刊登日期 (起)`) = CURDATE() - INTERVAL 1 DAY",
        "今天": "DATE(`刊登日期 (起)`) = CURDATE()",
    }
    if term in date_map:
        # This is a form of clarification, so we should record it.
        term_clarifications.append({"term": term, "type": "date_filter", "value": date_map[term]})
        # Continue to the next iteration of the node
        return ambiguity_resolver_node(state={**state, "term_clarifications": term_clarifications})

    # Handle other ambiguous terms by searching
    schema_tool = [tool for tool in all_tools if tool.name == "sql_db_schema"][0]
    schema_info = schema_tool.invoke({"table_names": "test_cue_list"})
    column_names = []
    if "CREATE TABLE" in schema_info:
        try:
            table_definition_part = schema_info.split("CREATE TABLE test_cue_list (", 1)[1]
            table_definition = table_definition_part.split(");", 1)[0]
            for line in table_definition.split('\n'):
                if line.strip().startswith('`'):
                    column_names.append(line.strip().split('`')[1])
        except IndexError:
            print(f"Failed to parse schema: {schema_info}")

    if not column_names:
        print(f"Could not extract column names from schema for term: {term}")
        # Decide to skip this term
        term_clarifications.append({"term": term, "type": "unresolved", "value": None})
        return ambiguity_resolver_node(state={**state, "term_clarifications": term_clarifications})

    search_tool = [tool for tool in all_tools if tool.name == "search_ambiguous_term"][0]
    tool_response = search_tool.invoke({"search_term": term, "column_names": column_names})

    if tool_response:
        # Ask user for clarification
        options_str = "\n".join([f"{i+1}. {opt['column']}: {opt['value']}" for i, opt in enumerate(tool_response)])
        clarification_message = (
            f"關於 '{term}'，我找到了以下可能的匹配項，請問您指的是哪一個？請回覆數字或完整名稱。\n"
            f"{options_str}"
        )
        messages.append(AIMessage(content=clarification_message))
        
        # Set pending state and wait for human input
        pending_clarification = {"term": term, "options": tool_response}
        return {
            "messages": messages,
            "pending_clarification": pending_clarification,
            "term_clarifications": term_clarifications,
            "current_stage": "human_in_the_loop",
        }
    else:
        # No matches found, mark as unresolved and continue
        messages.append(AIMessage(content=f"關於 '{term}'，我找不到任何匹配項。"))
        term_clarifications.append({"term": term, "type": "unresolved", "value": None})
        return ambiguity_resolver_node(state={**state, "messages": messages, "term_clarifications": term_clarifications})
