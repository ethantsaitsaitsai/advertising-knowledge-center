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
        raw_content = messages[-1].content
        
        # Handle block-style content vs. simple string content
        if isinstance(raw_content, list) and raw_content:
            user_response = raw_content[0].get("text", "").strip().lower()
        else:
            user_response = str(raw_content).strip().lower()

        term_to_clarify = pending_clarification.get("term")
        options = pending_clarification.get("options", [])

        # Handle 'confirmation' type (yes/no) question
        if pending_clarification.get("type") == "confirmation":
            if user_response in ["是", "yes", "y"]:
                option = options[0]
                term_clarifications.append({
                    "term": term_to_clarify,
                    "column": option["column"],
                    "value": option["value"],
                })
                print(f"Confirmed '{term_to_clarify}' as '{option['value']}'")
            else:
                term_clarifications.append({"term": term_to_clarify, "type": "unresolved", "value": None})
                print(f"User rejected the single match for '{term_to_clarify}'.")
            pending_clarification = {}
        
        # Handle 'multiple_choice' type question
        else:
            matched_option = None
            if user_response.isdigit():
                try:
                    choice_index = int(user_response) - 1
                    if 0 <= choice_index < len(options):
                        matched_option = options[choice_index]
                except (ValueError, IndexError):
                    pass
            
            if not matched_option:
                for option in options:
                    if user_response in option['value'].lower():
                        matched_option = option
                        break
            
            if matched_option:
                term_clarifications.append({
                    "term": term_to_clarify,
                    "column": matched_option["column"],
                    "value": matched_option["value"],
                })
                pending_clarification = {}
                print(f"Clarified '{term_to_clarify}' to '{matched_option['value']}' in column '{matched_option['column']}'")
            else:
                options_str = "\n".join([f"{i+1}. {opt['column']}: {opt['value']}" for i, opt in enumerate(options)])
                messages.append(AIMessage(content=f"抱歉，無法理解您的選擇。請從以下選項中選擇一個：\n{options_str}"))
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
    
    next_ambiguous_term = next((term for term in all_ambiguous_terms if term not in clarified_terms), None)

    if not next_ambiguous_term:
        print("All ambiguous terms have been clarified.")
        return {
            "term_clarifications": term_clarifications,
            "pending_clarification": {},
            "current_stage": "ambiguity_resolver",
        }

    # Step 3: Process the next ambiguous term
    term = next_ambiguous_term
    
    date_map = {"昨天": "DATE(`刊登日期 (起)`) = CURDATE() - INTERVAL 1 DAY", "今天": "DATE(`刊登日期 (起)`) = CURDATE()"}
    if term in date_map:
        term_clarifications.append({"term": term, "type": "date_filter", "value": date_map[term]})
        return ambiguity_resolver_node({**state, "term_clarifications": term_clarifications})

    schema_tool = [tool for tool in all_tools if tool.name == "sql_db_schema"][0]
    schema_info = schema_tool.invoke({"table_names": "test_cue_list"})
    column_names = [line.strip().split('`')[1] for line in schema_info.split('\n') if line.strip().startswith('`')]

    if not column_names:
        term_clarifications.append({"term": term, "type": "unresolved", "value": None})
        return ambiguity_resolver_node({**state, "term_clarifications": term_clarifications})

    search_tool = [tool for tool in all_tools if tool.name == "search_ambiguous_term"][0]
    tool_response = search_tool.invoke({"search_term": term, "column_names": column_names})

    if tool_response:
        if len(tool_response) == 1:
            option = tool_response[0]
            clarification_message = (
                f"關於 '{term}'，我只找到一個可能的匹配項：\n"
                f"{option['column']}: {option['value']}\n"
                f"請問這就是您要查詢的項目嗎？（請回覆 '是' 或 '否'）"
            )
            pending_clarification = {"term": term, "options": tool_response, "type": "confirmation"}
        else:
            options_str = "\n".join([f"{i+1}. {opt['column']}: {opt['value']}" for i, opt in enumerate(tool_response)])
            clarification_message = (
                f"關於 '{term}'，我找到了以下可能的匹配項，請問您指的是哪一個？請回覆數字或完整名稱。\n"
                f"{options_str}"
            )
            pending_clarification = {"term": term, "options": tool_response, "type": "multiple_choice"}
        
        messages.append(AIMessage(content=clarification_message))
        return {
            "messages": messages,
            "pending_clarification": pending_clarification,
            "term_clarifications": term_clarifications,
            "current_stage": "human_in_the_loop",
        }
    else:
        messages.append(AIMessage(content=f"關於 '{term}'，我找不到任何匹配項。"))
        term_clarifications.append({"term": term, "type": "unresolved", "value": None})
        return ambiguity_resolver_node({**state, "messages": messages, "term_clarifications": term_clarifications})
