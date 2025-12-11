from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
from config.llm import llm
from nodes.campaign_subgraph.state import CampaignSubState
from prompts.sql_generator_prompt import SQL_GENERATOR_PROMPT
from utils.schema_selector import get_relevant_schema

# Structured output
class SQLOutput(BaseModel):
    sql: str = Field(..., description="The executable MySQL query.")
    explanation: str = Field(..., description="Brief explanation.")

# We construct a prompt that combines the global definition with memory injection
FULL_PROMPT = SQL_GENERATOR_PROMPT + "\n\n" + """
# Context from Investigation
Internal Memory (Search Results/Thoughts):
{internal_memory}

Previous SQL Error:
{sql_error}

請生成 SQL。
"""

prompt = ChatPromptTemplate.from_messages([
    ("user", FULL_PROMPT)
])

chain = prompt | llm.with_structured_output(SQLOutput)

def generator_node(state: CampaignSubState):
    """
    Generates SQL based on Task + Memory.
    """
    print("DEBUG [CampaignGenerator] Generating SQL...")
    task = state["task"]
    memory = state.get("internal_thoughts", [])
    sql_error = state.get("sql_error")
    
    memory_str = "\n".join(memory) if memory else "None"
    
    # --- Schema Selection ---
    # Construct a query string for the selector
    query_str = f"Filters: {task.filters}, Metrics: {task.analysis_needs.get('metrics', [])}"
    if task.instruction_text:
        query_str += f", Instruction: {task.instruction_text}"
        
    print(f"DEBUG [CampaignGenerator] Selecting Schema for: {query_str[:50]}...")
    schema_md = get_relevant_schema(query_str, task.query_level)
    
    # Map task fields to prompt variables
    ids = getattr(task, 'campaign_ids', []) or []
    prompt_inputs = {
        "query_level": task.query_level,
        "filters": str(task.filters),
        "metrics": str(task.analysis_needs.get("metrics", [])),
        "confirmed_entities": str(task.filters.get("brands", []) + task.filters.get("entities", [])), # Legacy support
        "campaign_ids": str(ids),
        "internal_memory": memory_str,
        "sql_error": str(sql_error) if sql_error else "None",
        "schema_context": schema_md
    }
    
    result = chain.invoke(prompt_inputs)
    
    return {
        "generated_sql": result.sql,
        "retry_count": state.get("retry_count", 0) + 1
    }
