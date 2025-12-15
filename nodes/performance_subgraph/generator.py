from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from config.llm import llm
from config.registry import config
from nodes.performance_subgraph.state import PerformanceSubState
from prompts.clickhouse_generator_prompt import CLICKHOUSE_GENERATOR_PROMPT
from utils.document_loader import load_clickhouse_schema
import json

# Output Schema
class SQLOutput(BaseModel):
    sql: str = Field(..., description="The executable ClickHouse SQL query.")
    explanation: str = Field(..., description="Brief explanation.")

def performance_generator_node(state: PerformanceSubState):
    """
    Generates ClickHouse SQL based on state context.
    """
    # 1. State Prep
    task = state.get("task")
    ids = state.get("campaign_ids", [])
    format_ids = state.get("format_ids", []) or state.get("filters", {}).get("ad_format_ids", [])
    filters = state.get("filters", {})

    # CRITICAL FIX: Deep copy analysis_needs to avoid polluting original user_intent
    # If we modify the reference directly, user_intent.analysis_needs gets enriched dimensions
    # This breaks DataFusion's ability to extract user's ORIGINAL requirements
    original_needs = state.get("analysis_needs", {})
    if isinstance(original_needs, dict):
        import copy
        needs = copy.deepcopy(original_needs)  # Create independent copy
    else:
        needs = {}
    
    # Extract Instruction
    instruction_text = "None"
    if task and hasattr(task, "instruction_text"):
        instruction_text = task.instruction_text
    
    # Logic: Auto-fill Metrics if missing
    was_default = False
    generic_keywords = config.get_generic_keywords()
    requested_metrics = needs.get("metrics", [])
    
    # Simple check for specific metrics
    has_specific = False
    if requested_metrics:
        has_specific = any(m.lower() not in generic_keywords for m in requested_metrics)
        
    if not needs or not has_specific:
        print("DEBUG [PerfGenerator] Defaulting metrics to CTR, VTR, ER.")
        if "metrics" not in needs: needs["metrics"] = []
        # We don't overwrite if existing, just append? Or set default set.
        # Actually, SQL generation depends on what we ask.
        # If user asks for nothing specific, we give them the basics.
        # But 'needs' might be empty dict.
        default_metrics = config.get_default_performance_metrics()
        for m in default_metrics:
            if m not in needs["metrics"]: needs["metrics"].append(m)
        was_default = True

    # --- Context Enrichment (Playbook) ---
    if "dimensions" not in needs: needs["dimensions"] = []

    # CRITICAL: Filter out MySQL-only dimensions that don't exist in ClickHouse
    # ClickHouse summing_ad_format_events_view doesn't have Segment_Category, Budget, etc.
    # These dimensions come from MySQL (target_segments, pre_campaign tables)
    mysql_only_dims = ["Segment_Category", "segment_category", "Budget_Sum", "budget_sum", "Ad_Format", "ad_format"]
    # Note: "ad_format_type" exists in ClickHouse, so we keep it

    original_dims = needs["dimensions"].copy()
    needs["dimensions"] = [d for d in needs["dimensions"] if d not in mysql_only_dims]

    if len(original_dims) != len(needs["dimensions"]):
        removed = set(original_dims) - set(needs["dimensions"])
        print(f"DEBUG [PerfGenerator] Filtered out MySQL-only dimensions: {removed}")

    # 1. Base Dimensions
    base_dims = ["campaign_name", "cmpid"]
    for dim in base_dims:
        if dim not in needs["dimensions"]:
            needs["dimensions"].insert(0, dim)

    # 2. Format Context (ad_format_type exists in ClickHouse)
    format_keywords = ["format", "格式", "ad_format_type_id"]
    has_format_intent = any(k in str(needs).lower() for k in format_keywords)
    if has_format_intent or format_ids:
        if "ad_format_type" not in needs["dimensions"]:
            needs["dimensions"].append("ad_format_type")

    print(f"DEBUG [PerfGenerator] Enriched Dimensions: {needs['dimensions']}")

    # 2. Prompt Construction
    schema_md = load_clickhouse_schema()
    
    # Map variables to prompt
    # Note: CLICKHOUSE_GENERATOR_PROMPT expects specific keys
    date_range = filters.get("date_range", {})
    # Handle DateRange object or dict
    if hasattr(date_range, "start"):
        d_start = date_range.start
        d_end = date_range.end
    elif isinstance(date_range, dict):
        d_start = date_range.get("start")
        d_end = date_range.get("end")
    else:
        d_start, d_end = None, None
        
    # Fallback dates if missing
    if not d_start: d_start = "2024-01-01" # Or dynamic 'today - 7 days'
    if not d_end: d_end = "2025-12-31" # Or dynamic 'today'

    prompt = ChatPromptTemplate.from_messages([
        ("user", CLICKHOUSE_GENERATOR_PROMPT)
    ])
    
    chain = prompt | llm.with_structured_output(SQLOutput)
    
    inputs = {
        "cmpid_list": str(ids),
        "ad_format_type_id_list": str(format_ids) if format_ids else "None",
        "date_start": str(d_start),
        "date_end": str(d_end),
        "dimensions": str(needs.get("dimensions", [])),
        "metrics": str(needs.get("metrics", [])),
        "instruction_text": instruction_text, # Pass instruction
        "schema_context": schema_md
    }
    
    try:
        result = chain.invoke(inputs)
        return {
            "generated_sql": result.sql,
            "was_default_metrics": was_default,
            "retry_count": state.get("retry_count", 0) + 1
        }
    except Exception as e:
        print(f"DEBUG [PerfGenerator] LLM Error: {e}")
        return {
            "sql_error": str(e),
            "generated_sql": None
        }
