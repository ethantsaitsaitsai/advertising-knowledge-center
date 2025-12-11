from typing import List, Dict
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from config.llm import llm
from utils.schema_parser import parse_markdown_schema, get_glossary_content
import os

SCHEMA_FILE = os.path.join(os.getcwd(), "documents/mysql_schema_context.md")

class TableSelection(BaseModel):
    """Selected tables for the query."""
    selected_tables: List[str] = Field(..., description="List of table names required for the query.")
    reasoning: str = Field(..., description="Why these tables were selected.")

SELECTOR_SYSTEM_PROMPT = """你是一個資料庫架構師。你的任務是根據使用者的問題，從下方的 Table List 中挑選出「必須」用到的資料表。

**原則**:
1. **最小化原則**: 只選真正需要的表。
2. **完整性原則**: 如果需要 Join (例如查 Campaign 但需要 Client Name)，必須選關聯表。
3. **預算層級**:
   - 問「合約/總覽」-> 選 `cue_lists`
   - 問「活動/波段」-> 選 `one_campaigns`
   - 問「執行/格式」-> 選 `pre_campaign`
   - 問「受眾」-> 選 `target_segments` (通常需配 `pre_campaign`)

**Table List**:
{table_list}
"""

def get_relevant_schema(query: str, query_level: str = "strategy") -> str:
    """
    Dynamically selects relevant schema markdown based on the query.
    """
    tables, summaries = parse_markdown_schema(SCHEMA_FILE)
    glossary = get_glossary_content(SCHEMA_FILE)
    
    if not tables:
        return "Error: Schema file not found or empty."

    # 1. Construct Table List String
    table_list_str = "\n".join([f"- `{name}`: {desc}" for name, desc in summaries.items()])
    
    # 2. Invoke LLM to select
    prompt = ChatPromptTemplate.from_messages([
        ("system", SELECTOR_SYSTEM_PROMPT),
        ("user", "User Query: {query}\nQuery Level: {query_level}\n\nPlease select tables.")
    ])
    
    chain = prompt | llm.with_structured_output(TableSelection)
    
    try:
        selection = chain.invoke({"table_list": table_list_str, "query": query, "query_level": query_level})
        selected_names = selection.selected_tables
        print(f"DEBUG [SchemaSelector] Selected: {selected_names} (Reason: {selection.reasoning})")
    except Exception as e:
        print(f"DEBUG [SchemaSelector] LLM Error: {e}. Fallback to all.")
        selected_names = list(tables.keys())

    # 3. Assemble Markdown
    final_schema = "# Selected Database Schema\n\n"
    
    # Always include Core Glossary
    final_schema += "# Common Glossary\n" + glossary + "\n\n"
    
    for name in selected_names:
        if name in tables:
            final_schema += tables[name] + "\n\n"
        else:
            # Handle potential LLM hallucination of table names
            pass
            
    return final_schema
