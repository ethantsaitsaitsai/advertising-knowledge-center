from langchain_core.messages import HumanMessage, ToolMessage
from schemas.state import GraphState
from tools.tool_registry import all_tools


def ambiguity_resolver_node(state: GraphState) -> GraphState:
    """
    Resolves ambiguous terms in the query using the search_ambiguous_term tool.
    """
    print("---AMBIGUITY RESOLVER---")
    analysis_result = state["analysis_result"]
    ambiguous_terms = analysis_result.get("ambiguous_terms", [])
    original_query = state["query"]

    if not ambiguous_terms:
        print("No ambiguous terms found, skipping ambiguity resolution.")
        return {
            "clarified_query": original_query,
            "current_stage": "ambiguity_resolver",
        }

    clarified_query = original_query
    messages = state["messages"]
    date_filter = None

    # Define a map for date-related terms
    date_map = {
        "昨天": "DATE(`刊登日期 (起)`) = CURDATE() - INTERVAL 1 DAY",
        "今天": "DATE(`刊登日期 (起)`) = CURDATE()",
    }

    # Separate date terms from other ambiguous terms
    date_terms = [term for term in ambiguous_terms if term in date_map]
    other_terms = [term for term in ambiguous_terms if term not in date_map]

    # Handle date terms
    if date_terms:
        # For simplicity, we'll use the condition for the first date term found
        term = date_terms[0]
        date_filter = date_map[term]
        # Remove the date term from the query to avoid confusing the LLM later
        clarified_query = clarified_query.replace(term, "").strip()
        print(f"Applied date filter for '{term}': {date_filter}")

    # For each other ambiguous term, try to resolve it
    for term in other_terms:
        # First, get schema to find potential columns
        schema_tool = [tool for tool in all_tools if tool.name == "sql_db_schema"][0]
        schema_info = schema_tool.invoke({"table_names": "test_cue_list"})  # Assuming single table for now

        # This is a simplified parsing, a more robust solution might be needed
        column_names = []
        if "CREATE TABLE" in schema_info:
            # Split the schema info to isolate the column definitions
            try:
                table_definition_part = schema_info.split("CREATE TABLE test_cue_list (", 1)[1]
                table_definition = table_definition_part.split(");", 1)[0]
                for line in table_definition.split('\n'):
                    line = line.strip()
                    # Ensure the line defines a column (and not a key/constraint)
                    if line and line.startswith('`'):
                        col_name = line.split('`')[1]
                        column_names.append(col_name)
            except IndexError:
                print(f"Failed to parse schema: {schema_info}")

        if not column_names:
            print(f"Could not extract column names from schema for term: {term}")
            continue

        # Use search_ambiguous_term tool
        search_tool = [tool for tool in all_tools if tool.name == "search_ambiguous_term"][0]
        tool_response = search_tool.invoke({"search_term": term, "column_names": column_names})

        if tool_response:
            # If matches found, ask user for clarification
            clarification_message = f"關於 '{term}'，我找到了以下可能的匹配項：{', '.join(tool_response)}。請問您指的是哪一個？"
            messages.append(HumanMessage(content=clarification_message))
            # For now, we'll just add the clarification message and assume the user will respond
            # In a real interactive system, this would pause and wait for user input.
            # For this refactoring, we'll simulate a direct update for now.
            # A more advanced graph would have a "human_in_the_loop" node.

            # For demonstration, let's assume the first match is chosen if available
            if tool_response:
                clarified_query = clarified_query.replace(term, tool_response[0])
                messages.append(ToolMessage(tool_call_id="simulated_clarification",
                                            content=f"使用者確認將 '{term}' 替換為 '{tool_response[0]}'"))
        else:
            messages.append(HumanMessage(content=f"關於 '{term}'，我找不到任何匹配項。請提供更明確的資訊。 "))

    return {
        "clarified_query": clarified_query,
        "date_filter": date_filter,
        "current_stage": "ambiguity_resolver",
        "messages": messages,
    }
