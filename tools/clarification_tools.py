from typing import List, Dict
from langchain_core.tools import tool


@tool
def ask_user_for_clarification(term: str, options: List[Dict[str, str]]) -> str:
    """
    Asks the user for clarification when an ambiguous term is found.
    This tool should be used when you have identified an ambiguous term and have a list of possible options for the user to choose from.
    It will format the question and options, and the user's response will be captured in the next turn.

    Args:
        term: The ambiguous term that needs clarification.
        options: A list of dictionaries, where each dictionary represents a possible clarification. 
                 Each dictionary must have a 'column' and a 'value' key.

    Returns:
        A formatted string containing the question and the numbered options for the user.
    """
    if not options:
        return f"關於 '{term}'，我找不到任何具體的選項，但我需要更多資訊。"

    if len(options) == 1:
        option = options[0]
        return (
            f"關於 '{term}'，我只找到一個可能的匹配項：\n"
            f"{option['column']}: {option['value']}\n"
            f"請問這就是您要查詢的項目嗎？（請回覆 '是' 或 '否'）"
        )

    options_str = "\n".join([f"{i+1}. {opt['column']}: {opt['value']}" for i, opt in enumerate(options)])
    return (
        f"關於 '{term}'，我找到了以下可能的匹配項，請問您指的是哪一個？請回覆數字、完整名稱、或「全部」。\n"
        f"{options_str}"
    )
