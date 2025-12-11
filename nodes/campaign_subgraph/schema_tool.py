from langchain_community.tools.sql_database.tool import InfoSQLDatabaseTool, ListSQLDatabaseTool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import CommaSeparatedListOutputParser
from nodes.campaign_subgraph.state import CampaignSubState
from config.database import get_mysql_db
from config.llm import llm

# Initialize Selection Chain
# This mini-chain helps the agent pick relevant tables from a list.
SELECTION_SYSTEM_PROMPT = """你是一個資料庫專家。
你的任務是根據使用者的查詢需求 (Task)，從可用的資料表清單中，挑選出**最相關**的表名。

**選擇規則**:
1. 只選擇必要的表。
2. 根據 Query Level 選擇 Root Table (例如 contract -> cue_lists, strategy -> one_campaigns)。
3. 如果需要維度 (如 Agency, Ad_Format)，請選擇對應的維度表。
4. **回傳格式**: 僅回傳表名，用逗號分隔 (例如: `table1, table2`)。不要有其他文字。
"""

# Gemini Compatibility: Use User Message for dynamic input
SELECTION_USER_MESSAGE = """
**查詢需求**:
- Level: {query_level}
- Filters: {filters}
- Metrics/Dimensions: {analysis_needs}

**可用資料表**:
{table_list}

請列出最相關的表名。
"""

selection_prompt = ChatPromptTemplate.from_messages([
    ("system", SELECTION_SYSTEM_PROMPT),
    ("user", SELECTION_USER_MESSAGE)
])

selection_chain = selection_prompt | llm | CommaSeparatedListOutputParser()

def schema_tool_node(state: CampaignSubState):
    """
    Executes a smart schema inspection:
    1. List all tables.
    2. AI selects relevant tables based on task.
    3. Get schema for selected tables.
    """
    print("DEBUG [CampaignSchemaTool] step 1: Listing all tables...")
    
    db = get_mysql_db()
    task = state["task"]
    
    # Step 1: List all tables
    list_tool = ListSQLDatabaseTool(db=db)
    all_tables_str = list_tool.invoke("")
    
    # Step 2: AI Selects Relevant Tables
    print(f"DEBUG [CampaignSchemaTool] step 2: Selecting relevant tables for level '{task.query_level}'...")
    
    try:
        selected_tables = selection_chain.invoke({
            "query_level": task.query_level,
            "filters": str(task.filters),
            "analysis_needs": str(task.analysis_needs),
            "table_list": all_tables_str
        })
        
        # Clean up whitespace
        target_tables = [t.strip() for t in selected_tables if t.strip()]
        
        # Safety: If AI picks nothing, fallback to a sensible default based on logic (or just one_campaigns)
        if not target_tables:
            print("DEBUG [CampaignSchemaTool] AI selected no tables. Using fallback.")
            target_tables = ["one_campaigns"]
            
        print(f"DEBUG [CampaignSchemaTool] Selected: {target_tables}")
        
    except Exception as e:
        print(f"DEBUG [CampaignSchemaTool] Selection failed: {e}. Fallback to basic logic.")
        # Fallback logic (similar to previous version)
        if task.query_level == "contract":
            target_tables = ["cue_lists", "clients"]
        else:
            target_tables = ["one_campaigns", "pre_campaign"]

    # Step 3: Get Schema Info
    # InfoSQLDatabaseTool expects comma-separated string
    target_tables_str = ", ".join(target_tables)
    
    info_tool = InfoSQLDatabaseTool(db=db)
    try:
        schema_info = info_tool.invoke(target_tables_str)
    except Exception as e:
        schema_info = f"Error fetching schema: {e}"
    
    thought = f"Schema Inspection Result for [{target_tables_str}]:\n{schema_info}"
    
    return {
        "internal_thoughts": [thought]
    }
