from langchain_core.prompts import ChatPromptTemplate
from config.llm import llm
from schemas.presentation_plan import DataFramePresentationPlan
import pandas as pd
import json

PRESENTATION_PLANNER_PROMPT = """
You are a Data Presentation Expert.
Your task is to decide how to present a dataset to the user based on their query.

**Goal**:
Select the most relevant columns, rename them to be user-friendly, and determine the sorting order.

**User Query**:
"{user_query}"

**Available Columns (in the dataset)**:
{columns}

**Data Preview (First 2 rows)**:
{data_preview}

**Rules**:
1. **Relevance**: Only select columns that are directly relevant to the User Query.
2. **Identification**: ALWAYS keep 'Campaign_Name' (or similar) if it exists, so the user knows what they are looking at.
3. **Dimensions**: Keep dimension columns like 'Ad_Format', 'Segment_Category', 'Start_Date' if they contain useful info (not all None).
4. **Metrics**: Keep metrics requested by the user (e.g., CTR, Budget). If the user asks for "Performance", include standard metrics (Impression, Click, CTR, etc.).
5. **Cleanliness**:
   - **MUST REMOVE** technical IDs: 'cmpid', 'id', 'ad_format_type_id', 'segment_id', 'guid'.
   - **MUST REMOVE** redundant columns (e.g., if 'campaign_name' and 'Campaign_Name' both exist, keep the capitalized one).
   - **MUST REMOVE** empty columns (if you see they are empty in the preview).
6. **Renaming**: Rename columns to be friendly (e.g., 'budget_sum' -> '預算', 'ctr' -> 'CTR (%)').
7. **Sorting**: Sort by the most important metric (e.g., Budget or CTR) descending, unless the user implies a specific order (e.g., "by date").

**Output**:
Provide a structured plan.
"""

def generate_presentation_plan(user_query: str, df: pd.DataFrame) -> DataFramePresentationPlan:
    """
    Uses LLM to generate a plan for filtering, sorting, and renaming the DataFrame.
    """
    if df.empty:
        return DataFramePresentationPlan(keep_columns=[], rationale="Empty DataFrame")

    # Prepare context for LLM
    columns = list(df.columns)
    
    # Simple data preview (convert to string to avoid huge context)
    preview = df.head(2).to_dict(orient='records')
    
    prompt = ChatPromptTemplate.from_messages([
        ("user", PRESENTATION_PLANNER_PROMPT)
    ])
    
    chain = prompt | llm.with_structured_output(DataFramePresentationPlan)
    
    try:
        plan = chain.invoke({
            "user_query": user_query,
            "columns": str(columns),
            "data_preview": str(preview)
        })
        return plan
    except Exception as e:
        print(f"Error generating presentation plan: {e}")
        # Fallback: Return all columns (except obvious IDs) if LLM fails
        safe_cols = [c for c in columns if 'id' not in c.lower() or 'cmpid' not in c.lower()]
        return DataFramePresentationPlan(
            keep_columns=safe_cols,
            rationale="Fallback due to LLM error"
        )
