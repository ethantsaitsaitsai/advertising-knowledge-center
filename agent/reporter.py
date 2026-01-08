"""
Data Reporter Node for AKC Framework 3.0

Responsibilities:
1. Receive raw `data_store` from Retriever.
2. Use `pandas_processor` to Merge, Aggregage, and Format data.
3. Generate the final Markdown response.
"""
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from config.llm import llm
from agent.state import AgentState
from tools.data_processing_tool import pandas_processor
import json
import pandas as pd
import re

# Tools for Reporter (Pandas Only)
REPORTER_TOOLS = [pandas_processor]
llm_with_tools = llm.bind_tools(REPORTER_TOOLS)

REPORTER_SYSTEM_PROMPT = """你是 AKC 智能助手的資料報告專家 (Data Reporter)。

**你的任務**:
你從檢索者 (Retriever) 那裡接收到了原始數據 (`data_store`)。你的工作是將這些零散的數據整合成一張有意義的報表。

**原始數據概況**:
{data_summary}

**操作指南**:
1. **分析數據源**: 查看有哪些數據可用 (例如 `query_investment_budget` 有金額, `query_unified_performance` 有成效)。
2. **決定主表 (Anchor)**: 選擇涵蓋面最廣的表作為主表 (通常是 Investment, Execution 或 Format Benchmark 表)。
3. **執行合併 (Merge)**:
   - 使用 `pandas_processor(operation="merge", ...)`。
   - **這是必須的**。你不能分開顯示兩張表。你必須將投資金額、成效、受眾標籤合併在一起。
   - 如果有受眾標籤 (`query_targeting_segments`)，請先用 `groupby_concat` 把它壓扁成一行一筆，再 Merge。
   - **重要**: 若要合併「明細表」(如成效) 到「總表」(如預算)，請先將明細表 **聚合 (Aggregate)** 到相同顆粒度 (如 Campaign+Format)，避免金額重複計算。
4. **輸出 (Select Columns)**:
   - 使用 `select_columns` 指定使用者關心的欄位 (例如 `['廣告格式', '投資金額', '成效']`)。
   - 工具會自動處理成效指標的重算 (CTR/VTR)。

**禁止事項**:
- 禁止使用 SQL 工具 (你沒有權限)。
- 禁止在文字回應中自己畫 Markdown 表格 (工具會自動產生)。
- 禁止分開輸出多張小表。

**目標**: 產出一張包含「{user_query_intent}」相關所有維度的寬表。
"""

def data_reporter_node(state: AgentState) -> Dict[str, Any]:
    """
    Auto-Drive Reporter: Programmatically merges data and lets LLM summarize.
    """
    data_store = state.get("data_store", {})
    
    # --- Reconstruct data_store from messages if empty ---
    if not data_store:
        print("DEBUG [Reporter] data_store is empty. Reconstructing from ToolMessages...")
        from langchain_core.messages import ToolMessage
        
        tool_call_map = {}
        for msg in state.get("messages", []):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_call_map[tc["id"]] = tc["name"]
        
        for msg in state.get("messages", []):
            if isinstance(msg, ToolMessage):
                tool_name = tool_call_map.get(msg.tool_call_id)
                if not tool_name: continue
                
                try:
                    content = msg.content
                    if "\n\n✅" in content:
                        content = content.split("\n\n✅")[0]
                    
                    result = None
                    try:
                        result = json.loads(content)
                    except json.JSONDecodeError:
                        cleaned_content = content.replace("Decimal('", "").replace("')", "")
                        try:
                            import ast
                            result = ast.literal_eval(cleaned_content)
                        except:
                            continue

                    if isinstance(result, dict) and "data" in result:
                        data = result.get("data")
                        if isinstance(data, list):
                            if tool_name not in data_store:
                                data_store[tool_name] = []
                            
                            if data:
                                existing_data_str = {json.dumps(row, sort_keys=True, default=str) for row in data_store[tool_name]}
                                for row in data:
                                    row_str = json.dumps(row, sort_keys=True, default=str)
                                    if row_str not in existing_data_str:
                                        data_store[tool_name].append(row)
                                        existing_data_str.add(row_str)
                except Exception as e:
                    print(f"DEBUG [Reporter] Error processing {tool_name}: {e}")

    original_query = state.get("routing_context", {}).get("original_query", "")
    execution_logs = state.get("debug_logs", [])

    has_actual_data = any(len(rows) > 0 for rows in data_store.values() if isinstance(rows, list))
    
    if not data_store or not has_actual_data:
        msg = "抱歉，我在資料庫中沒有找到與「悠遊卡」相關的成效或預算數據。" if "悠遊卡" in original_query else "抱歉，我沒有找到相關數據。"
        return {
            "final_response": msg,
            "messages": [AIMessage(content=msg)],
            "debug_logs": execution_logs
        }

    print(f"DEBUG [Reporter] Auto-Drive Mode Activated. Processing {len(data_store)} datasets...")
    print(f"DEBUG [Reporter] Data Store Keys: {list(data_store.keys())}")

    # --- Pre-processing: Aggregate Investment Budget ---
    if "query_investment_budget" in data_store:
        print("DEBUG [Reporter] Pre-aggregating Investment Budget...")
        inv_data = data_store["query_investment_budget"]
        
        # 聚合至 Campaign + Format 層級，避免多個 CueList 導致重複
        groupby_keys = ["campaign_id", "format_name", "format_type_id", "client_name", "agency_name"]
        if inv_data:
            available_keys = [k for k in groupby_keys if k in inv_data[0]]
            
            res = pandas_processor.invoke({
                "data": inv_data,
                "operation": "groupby_sum",
                "groupby_col": ",".join(available_keys),
                "sum_col": "investment_amount",
                "sort_col": "campaign_id"
            })
            
            if res.get("status") == "success":
                data_store["query_investment_budget"] = res.get("data")
                print(f"DEBUG [Reporter] Aggregated Investment Budget to {len(res.get('data'))} rows.")

    # --- Auto-Drive Pipeline ---
    current_data = None

    # 1. Determine Anchor Table
    if "query_execution_budget" in data_store:
        current_data = data_store["query_execution_budget"]
        print("DEBUG [Reporter] Anchor: Execution Budget")
    elif "query_investment_budget" in data_store:
        current_data = data_store["query_investment_budget"]
        print("DEBUG [Reporter] Anchor: Investment Budget")
    elif "query_industry_format_budget" in data_store:
        current_data = data_store["query_industry_format_budget"]
        print("DEBUG [Reporter] Anchor: Industry Format Budget")
    elif "query_unified_performance" in data_store:
        current_data = data_store["query_unified_performance"]
        print("DEBUG [Reporter] Anchor: Unified Performance")
    elif "query_campaign_basic" in data_store:
        current_data = data_store["query_campaign_basic"]
        print("DEBUG [Reporter] Anchor: Campaign Basic")
    else:
        valid_keys = [k for k in data_store.keys() if k != "resolve_entity" and k != "id_finder"]
        if valid_keys:
            key = valid_keys[0]
            current_data = data_store[key]
            print(f"DEBUG [Reporter] Anchor: Fallback to {key}")
    
    if current_data:
        print(f"DEBUG [Reporter] Anchor Cols: {list(current_data[0].keys())[:10]}")

        # Filter out Direct Client for Agency queries
        agency_keywords = ['代理商', '代理', '廣告代理', 'agency']
        is_agency_query = any(kw in original_query.lower() for kw in agency_keywords)

        if is_agency_query and 'agency_name' in current_data[0]:
            current_data = [row for row in current_data if row.get('agency_name') != 'Direct Client']

    # 2. Process Segments (Flatten)
    if "query_targeting_segments" in data_store:
        # Check merge keys. Targeting usually has 'plaid' or 'campaign_id'
        has_plaid = current_data and ("plaid" in current_data[0] or "placement_id" in current_data[0])
        has_campaign = current_data and "campaign_id" in current_data[0]
        
        segments_data = data_store["query_targeting_segments"]
        
        # Priority: Merge by Plaid (More accurate) -> Campaign
        if has_plaid:
            print("DEBUG [Reporter] Merging Segments by Plaid...")
            # Normalize key
            seg_key = "plaid" if "plaid" in segments_data[0] else "placement_id"
            anchor_key = "plaid" if "plaid" in current_data[0] else "placement_id"
            
            # Rename segment key to match anchor if needed
            if seg_key != anchor_key:
                for row in segments_data:
                    if seg_key in row: row[anchor_key] = row.pop(seg_key)
            
            res = pandas_processor.invoke({
                "data": segments_data,
                "operation": "groupby_concat",
                "groupby_col": anchor_key,
                "concat_col": "segment_name",
                "new_col": "targeting_segments"
            })
            
            if res.get("status") == "success":
                current_data = pandas_processor.invoke({
                    "data": current_data,
                    "merge_data": res.get("data"),
                    "merge_on": anchor_key,
                    "operation": "merge",
                    "merge_how": "left"
                }).get("data")
                
        elif has_campaign:
            print("DEBUG [Reporter] Merging Segments by Campaign ID...")
            # Segments data might have campaign_id
            if "campaign_id" in segments_data[0]:
                res = pandas_processor.invoke({
                    "data": segments_data,
                    "operation": "groupby_concat",
                    "groupby_col": "campaign_id",
                    "concat_col": "segment_name",
                    "new_col": "targeting_segments"
                })
                if res.get("status") == "success":
                    current_data = pandas_processor.invoke({
                        "data": current_data,
                        "merge_data": res.get("data"),
                        "merge_on": "campaign_id",
                        "operation": "merge",
                        "merge_how": "left"
                    }).get("data")

    # 3. Merge Performance (The Inflation Fix)
    if "query_unified_performance" in data_store and current_data != data_store["query_unified_performance"]:
        print("DEBUG [Reporter] Merging Unified Performance...")
        perf_data = data_store["query_unified_performance"]
        
        # Normalize Keys
        for row in perf_data:
            if "cmpid" in row: row["campaign_id"] = row["cmpid"]
            
        # Determine Join Key and Granularity
        # If Anchor is Investment Budget, it is aggregated (Campaign + Format).
        # If Anchor is Execution Budget, it is Plaid level.
        
        has_plaid = "plaid" in current_data[0]
        has_format = "format_name" in current_data[0]
        
        if has_plaid:
            # Join by Plaid (1:1 usually) - Ideal
            print("DEBUG [Reporter] Performance Merge Strategy: Plaid Level")
            join_key = "plaid"
            # Ensure perf has plaid (it should)
        else:
            # Join by Campaign (+ Format if possible)
            print("DEBUG [Reporter] Performance Merge Strategy: Campaign Level (Pre-aggregation required)")
            
            join_key = "campaign_id"
            # Try to add Format to key
            if has_format and "ad_format_type" in perf_data[0]:
                # Normalize format names logic could go here, but let's stick to campaign_id for safety first
                # Or simplistic name matching
                pass

            # Pre-aggregate Performance to prevent inflation
            print(f"DEBUG [Reporter] Pre-aggregating performance by {join_key}")
            agg_res = pandas_processor.invoke({
                "data": perf_data,
                "operation": "groupby_sum",
                "groupby_col": join_key,
                "sum_col": "effective_impressions, clicks, total_q100_views, total_engagements",
                "top_n": 0
            })
            if agg_res.get("status") == "success":
                perf_data = agg_res.get("data")
            
        # Execute Merge
        res = pandas_processor.invoke({
            "data": current_data,
            "merge_data": perf_data,
            "merge_on": join_key,
            "operation": "merge",
            "merge_how": "left"
        })
        if res.get("status") == "success":
            current_data = res.get("data")

    # 4. Merge Campaign Basic (Enrichment)
    if "query_campaign_basic" in data_store and current_data != data_store["query_campaign_basic"]:
        if current_data and "campaign_id" in current_data[0]:
            print("DEBUG [Reporter] Enriching with Campaign Basic info...")
            res = pandas_processor.invoke({
                "data": current_data,
                "merge_data": data_store["query_campaign_basic"],
                "merge_on": "campaign_id",
                "operation": "merge",
                "merge_how": "left"
            })
            if res.get("status") == "success":
                current_data = res.get("data")

    # 5. Schema Planning & Output
    if current_data:
        available_cols = list(current_data[0].keys())
        print(f"DEBUG [Reporter] Planning Schema with cols: {available_cols}")
        
        # Load Mapping Config
        import os
        config_path = os.path.join(os.getcwd(), "config", "column_mapping.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                mapping_config = json.load(f)
                std_dict_str = json.dumps(mapping_config.get("standard_dictionary", {}), ensure_ascii=False, indent=2)
                expansion_str = json.dumps(mapping_config.get("concept_expansion", {}), ensure_ascii=False, indent=2)
        except Exception:
            std_dict_str = "{}"
            expansion_str = "{}"

        SCHEMA_PROMPT = f"""
        你是資料報表架構師。你的任務是將雜亂的 SQL 原始欄位轉換為使用者易讀的商業報表。
        
        使用者查詢: "{original_query}"
        
        目前資料表有以下欄位 (Raw Columns):
        {available_cols}
        
        請根據使用者查詢，設計最後的表格架構。請嚴格遵守以下標準：

        **1. AKC 標準欄位字典 (Standard Dictionary)**:
        請務必參考此字典進行 Rename：
        {std_dict_str}

        **2. 概念自動展開 (Concept Expansion) - 最高優先級**:
        如果使用者查詢了以下概念，**必須**將對應的**所有**指標加入 `display_columns`：
        {expansion_str}

        ⚠️ **重要規則**:
        - 概念展開的欄位等同於使用者明確要求，必須全部顯示。
        - **智能精簡**: 當使用者要求「成效」時：
          - 如果資料中同時有「點擊率 (CTR%)」「觀看率 (VTR%)」「互動率 (ER%)」**以及**「有效曝光」「總點擊」
          - 則**只顯示比率指標**（CTR/VTR/ER），**隱藏原始指標**（有效曝光、總點擊、完整觀看數、總互動）
          - 原因：比率指標已經包含了成效資訊，顯示原始數據會造成表格冗餘
        - 但如果只有原始指標（有效曝光、總點擊）而沒有比率，則必須顯示原始指標

        **3. 佔比計算規則 (Percentage Calculation)**:
        - 如果使用者查詢包含「**佔比**」、「**比例**」、「**分佈**」、「**Share**」：
          - 必須在 `percentage_config` 中指定要計算佔比的欄位（通常是投資金額）。
          - 格式: `{{"column": "investment_amount", "new_col": "投資金額佔比%"}}`

        **4. 欄位排序規則 (Column Ordering)**:
        請按照以下順序排列 `display_columns`：
        1. **主鍵** (Primary Key): 通常是「廣告格式」或「活動名稱」
        2. **文字型欄位** (Text Fields): 如「受眾標籤」「活動名稱」等描述性欄位
        3. **數值型欄位** (Numeric Fields): 如「投資金額」「投資金額佔比%」「點擊率 (CTR%)」等數字指標

        **5. 輸出要求**:
        - **rename_map**: 原始欄位 -> 標準中文名稱（用於最終顯示）。
        - **display_columns**: 最終要顯示的欄位列表（使用中文名稱）。
          - **規則**: 顯示主鍵 + 使用者明確要求的欄位 + 概念展開的欄位 + **佔比欄位**(若有)。
          - **禁止**: 嚴禁出現「客戶名稱」「代理商」「活動編號」「cmpid」「plaid」「format_type_id」「cue_list_id」等內部欄位，除非使用者明確詢問。
          - **嚴格過濾**: 只有在使用者明確要求（或概念展開需要）時才顯示「廣告格式」。
        - **groupby_cols**: 用於去重的維度欄位 (英文名)。
        - **sum_cols**: 用於加總的指標欄位 (英文名)。
        - **concat_col**: 用於字串聚合的欄位 (英文名)。
        - **sort_col**: 排序欄位 (如 "ctr DESC")。
        - **limit**: 限制顯示筆數（整數）。如果使用者要「前X」則設為 X，否則設為 0。
        - **time_aggregation**: 時間聚合配置。
        - **percentage_config**: 佔比計算配置 (例如 `{{"column": "investment_amount", "new_col": "投資金額佔比%"}}`)。

        請直接回傳 JSON 格式，不要包含任何 Markdown 標記或文字說明。
        """
        
        try:
            # LLM Planning call
            plan_response = llm.invoke([
                SystemMessage(content="You are a JSON generator. Output only valid raw JSON without any markdown formatting."),
                HumanMessage(content=SCHEMA_PROMPT)
            ])
            content = plan_response.content
            if isinstance(content, list): content = " ".join([c.get("text", "") for c in content])
            
            content = content.replace("```json", "").replace("```", "").strip()
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                plan = json.loads(json_match.group(0))
                
                # ... (Schema Optimizer Logic - kept same as before) ...
                
                # Auto-inject Performance Raw Metrics into sum_cols
                rate_metrics = ["ctr", "vtr", "er"]
                raw_metrics_map = {
                    "ctr": ["effective_impressions", "total_impressions", "total_clicks", "clicks"],
                    "vtr": ["total_q100_views", "total_q100", "effective_impressions", "total_impressions"],
                    "er": ["total_engagements", "effective_impressions", "total_impressions"]
                }
                
                # Build reverse mapping
                reverse_map = {v: k for k, v in plan.get("rename_map", {}).items()}
                
                sum_cols_en = []
                for col in plan.get("sum_cols", []):
                    sum_cols_en.append(reverse_map.get(col, col))
                
                requested_cols_en = []
                for col_cn in plan.get("display_columns", []):
                    requested_cols_en.append(reverse_map.get(col_cn, col_cn))
                
                # --- Robust Sort Logic & Default Fallback ---
                sort_col_val = plan.get("sort_col")
                
                # If LLM didn't provide a sort, pick a smart default based on business rules
                if not sort_col_val:
                    # Priorities: Rate Metrics > Money > Volume
                    priority_metrics = ["ctr", "vtr", "er", "investment_amount", "execution_amount", "clicks", "effective_impressions"]
                    for metric in priority_metrics:
                        if metric in available_cols:
                            sort_col_val = f"{metric} DESC"
                            print(f"DEBUG [Reporter] Auto-assigned default sort: {sort_col_val}")
                            break
                
                # Safe split (fixes NoneType error)
                sort_col_raw = sort_col_val.split(" ")[0] if sort_col_val else ""
                
                # Ensure sort column is included in selection if valid
                if sort_col_raw and sort_col_raw not in requested_cols_en:
                     requested_cols_en.append(sort_col_raw)
                
                # Update plan for downstream use
                plan["sort_col"] = sort_col_val

                # --- State-Driven Column Inclusion ---
                # If specific tools were called and returned data, we force those columns to be shown.
                # This ensures that if the Analyst decided to fetch data, the Reporter MUST show it,
                # even if the LLM Planning step accidentally missed it.
                if "query_targeting_segments" in data_store and data_store["query_targeting_segments"]:
                    col_en = "targeting_segments"
                    col_cn = "受眾標籤"
                    
                    if col_en in available_cols and col_cn not in plan.get("display_columns", []):
                        print(f"DEBUG [Reporter] State-driven: Forcing inclusion of '{col_cn}' because segments data exists.")
                        # Insert at second position (after Primary Key)
                        plan["display_columns"].insert(1, col_cn)
                        
                        # Sync requested_cols_en for metric injection logic below
                        if col_en not in requested_cols_en:
                            requested_cols_en.append(col_en)
                        
                        # Ensure it's in concat_col for the pandas aggregation
                        if not concat_col_en:
                            concat_col_en = col_en
                        elif col_en not in concat_col_en:
                            concat_col_en += f",{col_en}"

                for rate in rate_metrics:
                    if any(rate in col.lower() for col in requested_cols_en):
                        raws = raw_metrics_map.get(rate, [])
                        for raw in raws:
                            if raw not in sum_cols_en and raw in available_cols:
                                sum_cols_en.append(raw)

                # Prepare processor args
                groupby_cols_en = [reverse_map.get(col, col) for col in plan.get("groupby_cols", [])]
                concat_col_en = plan.get("concat_col", "")
                if concat_col_en in reverse_map: concat_col_en = reverse_map[concat_col_en]
                
                # Ensure percentage base column is in sum_cols
                perc_config = plan.get("percentage_config")
                if perc_config and perc_config.get("column"):
                    base_col = perc_config.get("column")
                    if base_col not in sum_cols_en and base_col in available_cols:
                        sum_cols_en.append(base_col)

                # Execute Final Aggregation
                final_result = pandas_processor.invoke({
                    "data": current_data,
                    "operation": "groupby_sum",
                    "rename_map": plan.get("rename_map", {}),
                    "groupby_col": ",".join(groupby_cols_en),
                    "sum_col": ",".join(sum_cols_en),
                    "concat_col": concat_col_en,
                    "select_columns": plan.get("display_columns", []),
                    "sort_col": plan.get("sort_col"),
                    "percentage_config": perc_config, # [NEW] Pass percentage config
                    "ascending": False,
                    "top_n": plan.get("limit", 0)
                })

            else:
                raise ValueError("No valid JSON found in LLM response")

        except Exception as e:
            print(f"DEBUG [Reporter] Planning failed ({e}). Fallback to simple top_n.")
            fallback_select = [c for c in available_cols if not c.lower().endswith('id')]
            final_result = pandas_processor.invoke({
                "data": current_data,
                "operation": "top_n", 
                "top_n": 100,
                "select_columns": fallback_select[:7], 
                "sort_col": available_cols[0]
            })
    else:
        final_result = {"markdown": ""}

    final_table = final_result.get("markdown", "")
    
    # --- LLM Summary Generation ---
    start_date = state.get("routing_context", {}).get("start_date", "指定期間")
    end_date = state.get("routing_context", {}).get("end_date", "指定期間")
    
    SUMMARY_PROMPT = """
    你是數據報告呈現者。請針對使用者查詢「{query}」與生成的數據表產出回應。
    
    請回傳 JSON 格式，包含以下欄位：
    1. "suggestions": 根據數據結果，提供 3 個具體且高度相關的後續查詢建議（帶有 💡 符號與標題）。
    
    **規則**:
    - **嚴禁分析**: 不要在輸出中包含任何數據解讀或總結。
    - **JSON 格式**: 只回傳原始 JSON，不要包含 Markdown 標記。
    """
    
    opening_text = f"這是 **{start_date}** 至 **{end_date}** 期間，關於『{original_query}』的數據資料。"
    suggestions_text = ""

    if final_table:
        try:
            messages = [
                SystemMessage(content="You are a JSON generator. Output only valid raw JSON."),
                HumanMessage(content=SUMMARY_PROMPT.format(query=original_query))
            ]
            response = llm.invoke(messages)
            content = response.content
            if isinstance(content, list): content = " ".join([c.get("text", "") for c in content])
            
            content = content.replace("```json", "").replace("```", "").strip()
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                res_json = json.loads(json_match.group(0))
                suggestions_data = res_json.get("suggestions", "")
                if isinstance(suggestions_data, list):
                    suggestions_text = "\n".join(suggestions_data)
                else:
                    suggestions_text = str(suggestions_data)
        except Exception as e:
            print(f"DEBUG [Reporter] Summary JSON parsing failed: {e}")
    else:
        opening_text = "抱歉，無法從數據中生成報表。"

    final_response = opening_text + "\n\n" + final_table
    if suggestions_text:
        final_response += "\n\n" + suggestions_text

    # Sanitization
    final_response = final_response.strip()
    if final_response.startswith("```"):
        final_response = re.sub(r"^```[a-zA-Z]*\n?", "", final_response)
        final_response = re.sub(r"\n?```$", "", final_response)
    final_response = final_response.strip()

    return {
        "final_response": final_response,
        "messages": [AIMessage(content=final_response)],
        "debug_logs": execution_logs
    }