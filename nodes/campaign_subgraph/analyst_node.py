from typing import Dict, Any, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from config.llm import llm
from nodes.campaign_subgraph.state import CampaignSubState
from tools.campaign_template_tool import (
    query_campaign_financials, 
    query_campaign_formats, 
    query_campaign_deep_dive, 
    query_campaign_master
)
from tools.data_processing_tool import pandas_processor
import json

# 定義可用工具
TOOLS = [
    query_campaign_financials,
    query_campaign_formats,
    query_campaign_deep_dive,
    query_campaign_master,
    pandas_processor
]

# 綁定工具到 LLM
llm_with_tools = llm.bind_tools(TOOLS)

ANALYST_SYSTEM_PROMPT = """
你是一名資深媒體數據分析師，負責查詢 MySQL 資料庫。
你擁有一系列 SQL 模板工具，能處理財務、格式與細節查詢。

**工作規範**:
1. 分析使用者指令，選擇最適合的 SQL 模板工具。
2. 執行完 SQL 模板後，**必須**呼叫 `pandas_processor` 來加工與展示數據。
3. **重要**：呼叫 `pandas_processor` 時，請將 `data` 參數設為空列表 `[]`。系統會自動將上一步查詢到的完整數據注入進去。
4. **輸出規範**：工具執行成功後，任務即算完成，不需要多做解釋。

**工具選擇建議**:
- 涉及「YTD」、「認列金額」、「預算彙整」、「代理商業績」 -> query_campaign_financials
- 涉及「格式佔比」、「格式投資金額」、「執行金額統計」 -> query_campaign_formats
- 涉及「詳細設定」、「悠遊卡詳細資料」、「數據鎖定條件」 -> query_campaign_deep_dive
- 如果已知特定的實體 ID (ID: {entity_id}, Type: {entity_type}) 且要看一般清單 -> query_campaign_master

**當前情境**:
- 已解析實體: {entity_name}
- 實體 ID: {entity_id}
- 實體類型: {entity_type}

請根據使用者指令開始工作。
"""

def analyst_node(state: CampaignSubState):
    """
    Data Analyst Agent: Decides which tool to use and processes results.
    Implements 'Early Exit' strategy to prevent LLM hallucinations.
    """
    eid = state.get("resolved_entity_id")
    etype = state.get("resolved_entity_type")
    ename = state.get("resolved_entity_name")
    task = state["task"]
    instruction = task.instruction_text or str(task.analysis_needs)

    print(f"DEBUG [CampaignAnalyst] Agent working for {ename}...")

    messages = [
        SystemMessage(content=ANALYST_SYSTEM_PROMPT.format(
            entity_name=ename, 
            entity_id=eid, 
            entity_type=etype
        )),
        HumanMessage(content=f"使用者指令：{instruction}")
    ]

    internal_thoughts = []
    final_data = None
    
    # 增加迴圈次數，容許 Retry
    for i in range(5):
        print(f"DEBUG [CampaignAnalyst] Iteration {i+1}")
        response = llm_with_tools.invoke(messages)
        messages.append(response)
        
        # --- 檢查 Agent 是否想結束對話 ---
        if not response.tool_calls:
            # Retry 機制：如果有數據但沒表格，強制糾正
            if final_data and final_data.get("data"):
                print("DEBUG [CampaignAnalyst] Retry Triggered: Data exists but no pandas call.")
                warning_msg = "系統提示：你已經成功查詢到 SQL 數據，但尚未呼叫 `pandas_processor` 產生報表。請**立即**呼叫該工具 (data=[]) 以完成任務。"
                messages.append(HumanMessage(content=warning_msg))
                internal_thoughts.append("System: Retry triggered (missing pandas call).")
                continue 
            
            # 正常結束 (沒有數據也沒有工具呼叫，可能是單純對話)
            print("DEBUG [CampaignAnalyst] No tool calls, finishing.")
            return {
                "internal_thoughts": internal_thoughts,
                "campaign_data": final_data,
                "final_response": response.content,
                "next_action": "finish"
            }
        
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            args = tool_call["args"]
            
            print(f"DEBUG [CampaignAnalyst] Calling Tool: {tool_name}")
            internal_thoughts.append(f"Calling {tool_name}...")

            # --- 特殊處理：pandas_processor 數據注入 ---
            if tool_name == "pandas_processor":
                if final_data and final_data.get("data"):
                     print(f"DEBUG [CampaignAnalyst] Injecting cached data ({len(final_data['data'])} rows) into pandas_processor.")
                     args["data"] = final_data["data"]
                elif not args.get("data"):
                     args["data"] = []

            # 執行工具
            tool_map = {
                "query_campaign_financials": query_campaign_financials,
                "query_campaign_formats": query_campaign_formats,
                "query_campaign_deep_dive": query_campaign_deep_dive,
                "query_campaign_master": query_campaign_master,
                "pandas_processor": pandas_processor
            }
            
            tool_func = tool_map.get(tool_name)
            if tool_func:
                try:
                    result = tool_func.invoke(args)
                except Exception as e:
                    result = f"Error executing tool: {e}"

                # Case A: SQL Tool -> Cache Data
                if "query_campaign" in tool_name and isinstance(result, dict) and result.get("status") == "success":
                    final_data = result
                    row_count = result.get("count", 0)
                    print(f"DEBUG [CampaignAnalyst] SQL Tool returned {row_count} rows. Caching.")
                    
                    llm_result = {
                        "status": "success",
                        "count": row_count,
                        "columns": list(result["data"][0].keys()) if row_count > 0 else [],
                        "note": "Data cached. Use pandas_processor with data=[] to analyze.",
                        "sample": result["data"][:1] if row_count > 0 else []
                    }
                    messages.append(ToolMessage(tool_call_id=tool_call["id"], content=json.dumps(llm_result, ensure_ascii=False)))

                # Case B: Pandas Tool -> Capture Markdown directly AND EARLY EXIT
                elif tool_name == "pandas_processor" and isinstance(result, str):
                    print("DEBUG [CampaignAnalyst] Captured Markdown table. Early Exiting.")
                    
                    # 這是最關鍵的一步：直接回傳結果，切斷 LLM 的後續生成
                    final_response = "### 分析報告\n\n根據您的需求，已為您彙整以下數據：\n\n" + result
                    return {
                        "internal_thoughts": internal_thoughts,
                        "campaign_data": final_data,
                        "final_response": final_response,
                        "next_action": "finish"
                    }

                else:
                    messages.append(ToolMessage(tool_call_id=tool_call["id"], content=str(result)))

            else:
                messages.append(ToolMessage(
                    tool_call_id=tool_call["id"],
                    content=f"Error: Tool {tool_name} not found."
                ))

    # Fallback (迴圈結束仍無結果)
    return {
        "internal_thoughts": internal_thoughts,
        "campaign_data": final_data,
        "final_response": "抱歉，分析過程超時，未能產生完整報表。",
        "next_action": "finish"
    }
