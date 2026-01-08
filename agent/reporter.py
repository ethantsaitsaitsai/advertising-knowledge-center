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
2. **決定主表 (Anchor)**: 選擇涵蓋面最廣的表作為主表 (通常是 Investment 或 Format 表)。
3. **執行合併 (Merge)**:
   - 使用 `pandas_processor(operation="merge", ...)`。
   - **這是必須的**。你不能分開顯示兩張表。你必須將投資金額、成效、受眾標籤合併在一起。
   - 如果有受眾標籤 (`query_targeting_segments`)，請先用 `groupby_concat` 把它壓扁成一行一筆，再 Merge。
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
    data_store = state.get("data_store", {}) or {}
    
    # --- [NEW] Reconstruct data_store from messages if empty ---
    # This ensures compatibility with agents that don't manually update data_store (like create_agent)
    if not data_store:
        print("DEBUG [Reporter] data_store is empty. Reconstructing from ToolMessages...")
        from langchain_core.messages import ToolMessage
        
        # We need a way to know which tool produced which message.
        tool_call_map = {}
        for msg in state.get("messages", []):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_call_map[tc["id"]] = tc["name"]
        
        for msg in state.get("messages", []):
            if isinstance(msg, ToolMessage):
                tool_name = tool_call_map.get(msg.tool_call_id)
                if not tool_name: continue
                
                print(f"DEBUG [Reporter] Parsing {tool_name} message: {msg.content[:100]}...")
                try:
                    # Clean content (might have guidance text appended)
                    content = msg.content
                    if "\n\n✅" in content:
                        content = content.split("\n\n✅")[0]
                    
                    # Try to parse content
                    result = None
                    try:
                        result = json.loads(content)
                    except json.JSONDecodeError:
                        # Fallback for Python-style dict strings (single quotes)
                        # We use a safer way to handle some common non-JSON types if they exist
                        cleaned_content = content.replace("Decimal('", "").replace("')", "")
                        try:
                            import ast
                            result = ast.literal_eval(cleaned_content)
                        except:
                            print(f"DEBUG [Reporter] Failed to parse content for {tool_name}")
                            continue

                    if isinstance(result, dict) and "data" in result:
                        data = result.get("data")
                        # [FIX] Allow empty lists to be stored so we know the tool was called but returned nothing
                        if isinstance(data, list):
                            if tool_name not in data_store:
                                data_store[tool_name] = []
                            
                            # Deduplicate (only if not empty)
                            if data:
                                existing_data_str = {json.dumps(row, sort_keys=True, default=str) for row in data_store[tool_name]}
                                for row in data:
                                    row_str = json.dumps(row, sort_keys=True, default=str)
                                    if row_str not in existing_data_str:
                                        data_store[tool_name].append(row)
                                        existing_data_str.add(row_str)
                                print(f"DEBUG [Reporter] Reconstructed {len(data)} rows for {tool_name}")
                            else:
                                print(f"DEBUG [Reporter] Reconstructed 0 rows (Empty) for {tool_name}")
                except Exception as e:
                    print(f"DEBUG [Reporter] Error processing {tool_name}: {e}")

    original_query = state.get("routing_context", {}).get("original_query", "")
    execution_logs = state.get("debug_logs", [])

    # [STRICT FIX] Verify that at least one tool returned ACTUAL data rows
    has_actual_data = any(len(rows) > 0 for rows in data_store.values() if isinstance(rows, list))
    
    if not data_store or not has_actual_data:
        msg = "抱歉，我在資料庫中沒有找到與「悠遊卡」相關的成效或預算數據。" if "悠遊卡" in original_query else "抱歉，我沒有找到相關數據。"
        return {
            "final_response": msg,
            "messages": [AIMessage(content=msg)],
            "debug_logs": execution_logs
        }

    print(f"DEBUG [Reporter] Auto-Drive Mode Activated. Processing {len(data_store)} datasets...")
    print(f"DEBUG [Reporter] Data Store Keys: {list(data_store.keys())}") # [DEBUG] Print keys

    # --- Pre-processing: Aggregate Investment Budget ---
    # Fix for Many-to-Many explosion: Group investment by Campaign + Format before merging
    if "query_investment_budget" in data_store:
        print("DEBUG [Reporter] Pre-aggregating Investment Budget...")
        inv_data = data_store["query_investment_budget"]
        
        # We want to sum 'investment_amount' but keep other descriptor columns.
        # Strategy: Group by ID/Name keys, sum Amount, keep others as is (first).
        
        # 1. Identify GroupBy Keys (Unique Identifier for a row in the final table)
        # Usually Campaign + Format is the granularity users want.
        groupby_keys = ["campaign_id", "format_name", "format_type_id", "client_name", "agency_name"]
        
        # Filter keys that actually exist in the data
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

    # [NEW] Special Case: Client-Level Performance Aggregation
    # When both unified_performance and campaign_basic exist, check if user wants client-level breakdown
    if "query_unified_performance" in data_store and "query_campaign_basic" in data_store:
        client_keywords = ["客戶", "client", "廣告主", "品牌"]
        is_client_query = any(kw in original_query.lower() for kw in client_keywords)

        if is_client_query:
            print("DEBUG [Reporter] Detected client-level performance query. Performing cross-DB aggregation...")

            # Merge unified_performance with campaign_basic on cmpid/campaign_id
            perf_data = data_store["query_unified_performance"]
            campaign_data = data_store["query_campaign_basic"]
            
            # Ensure join key exists
            for row in campaign_data:
                if "campaign_id" in row and "cmpid" not in row:
                    row["cmpid"] = row["campaign_id"]

            # Use pandas_processor to merge
            merged_result = pandas_processor.invoke({
                "data": perf_data,
                "merge_data": campaign_data,
                "merge_on": "cmpid",
                "operation": "merge",
                "merge_how": "left"
            })

            if merged_result.get("status") == "success":
                current_data = merged_result.get("data")
                print(f"DEBUG [Reporter] Cross-DB merge successful: {len(current_data)} rows")
                
                # Override anchor selection - use merged data directly
                data_store["_client_performance_merged"] = current_data

    # 1. Determine Anchor Table (主表)
    # Priority: Client Performance Merged > Execution > Investment > Industry Format > Format Benchmark > Performance > Campaign > Others
    # Note: resolve_entity should NEVER be used as anchor - it's only for ID lookup

    if "_client_performance_merged" in data_store:
        current_data = data_store["_client_performance_merged"]
        print("DEBUG [Reporter] Anchor: Client Performance (Merged)")
    elif "query_execution_budget" in data_store:
        current_data = data_store["query_execution_budget"]
        print("DEBUG [Reporter] Anchor: Execution Budget")
    elif "query_investment_budget" in data_store:
        current_data = data_store["query_investment_budget"]
        print("DEBUG [Reporter] Anchor: Investment Budget")
    elif "query_industry_format_budget" in data_store: # [NEW] High Priority for Industry Queries
        current_data = data_store["query_industry_format_budget"]
        print("DEBUG [Reporter] Anchor: Industry Format Budget")
    elif "query_unified_performance" in data_store: # [NEW] High Priority for Unified Performance
        current_data = data_store["query_unified_performance"]
        print("DEBUG [Reporter] Anchor: Unified Performance (ClickHouse)")
    elif "query_format_benchmark" in data_store: # [NEW] High Priority for Format Benchmarks
        current_data = data_store["query_format_benchmark"]
        print("DEBUG [Reporter] Anchor: Format Benchmark")
    elif "query_campaign_basic" in data_store:
        current_data = data_store["query_campaign_basic"]
        print("DEBUG [Reporter] Anchor: Campaign Basic")
    else:
        # Fallback: take the first non-resolve_entity table
        valid_keys = [k for k in data_store.keys() if k != "resolve_entity"]
        if valid_keys:
            key = valid_keys[0]
            current_data = data_store[key]
            print(f"DEBUG [Reporter] Anchor: Fallback to {key}")
        else:
            # Last resort: even resolve_entity, but this should rarely happen
            key = list(data_store.keys())[0]
            current_data = data_store[key]
            print(f"DEBUG [Reporter] Anchor: Last resort fallback to {key}")
    
    if current_data:
        print(f"DEBUG [Reporter] Anchor Cols: {list(current_data[0].keys())[:10]}")

        # --- [NEW] Smart Filtering: Remove "Direct Client" for Agency Queries ---
        # When user asks about agencies, filter out "Direct Client" (non-agency records)
        agency_keywords = ['代理商', '代理', '廣告代理', 'agency']
        is_agency_query = any(kw in original_query.lower() for kw in agency_keywords)

        if is_agency_query and current_data:
            # Check if data has agency_name column
            if 'agency_name' in current_data[0]:
                original_count = len(current_data)
                current_data = [row for row in current_data if row.get('agency_name') != 'Direct Client']
                filtered_count = len(current_data)
                print(f"DEBUG [Reporter] Filtered out Direct Client: {original_count} → {filtered_count} rows")

        if not current_data:
            return {
                "final_response": "抱歉，過濾後沒有找到相關數據。",
                "messages": [AIMessage(content="抱歉，過濾後沒有找到相關數據。")]
            }

    # 2. Process Segments (Flatten)
    if "query_targeting_segments" in data_store:
        # [FIX] Check if merge key exists in anchor before attempting merge
        # Targeting segments can be linked by campaign_id OR placement_id.
        has_campaign_id = current_data and "campaign_id" in current_data[0]
        has_plaid = current_data and "plaid" in current_data[0]
        
        if has_campaign_id or has_plaid:
            print("DEBUG [Reporter] Processing Segments (Groupby Concat)...")
            
            # Determine merge key for Segments side
            # query_targeting_segments usually has both campaign_id and placement_id
            
            # Case A: Merge by Campaign ID
            if has_campaign_id:
                print("DEBUG [Reporter] Merging Segments by Campaign ID...")
                res = pandas_processor.invoke({
                    "data": data_store["query_targeting_segments"],
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
            
            # Case B: Merge by Placement ID (plaid)
            # Only if Campaign ID merge didn't happen or we want granular placement targeting
            elif has_plaid:
                print("DEBUG [Reporter] Merging Segments by Placement ID (plaid)...")
                
                # We need to map 'placement_id' in targeting data to 'plaid'
                segments_data = data_store["query_targeting_segments"]
                for row in segments_data:
                    if "placement_id" in row:
                        row["plaid"] = row["placement_id"]
                
                # Aggregate segments by plaid
                res = pandas_processor.invoke({
                    "data": segments_data,
                    "operation": "groupby_concat",
                    "groupby_col": "plaid",
                    "concat_col": "segment_name",
                    "new_col": "targeting_segments"
                })
                
                if res.get("status") == "success":
                    current_data = pandas_processor.invoke({
                        "data": current_data,
                        "merge_data": res.get("data"),
                        "merge_on": "plaid",
                        "operation": "merge",
                        "merge_how": "left"
                    }).get("data")

            if current_data:
                print(f"DEBUG [Reporter] After Segments Merge Cols: {list(current_data[0].keys())[:10]}")
        else:
            print("DEBUG [Reporter] Skipping Segments Merge: Neither 'campaign_id' nor 'plaid' found in anchor table.")

    # [NEW] Hybrid Merge Strategy (Unified Performance + Media Placements)
    # This connects ClickHouse Performance (plaid) with MySQL Budget (placement_id)
    if "query_unified_performance" in data_store and "query_media_placements" in data_store:
        print("DEBUG [Reporter] Executing Hybrid Merge (Performance + Budget)...")
        perf_data = data_store["query_unified_performance"]
        budget_data = data_store["query_media_placements"]
        
        # Strategy: Rename 'placement_id' in budget_data to 'plaid' BEFORE merge
        # This is required because pandas_processor merge_on expects a single key (or same key name)
        for row in budget_data:
            if "placement_id" in row:
                row["plaid"] = row["placement_id"] # Create alias
        
        # Now merge on 'plaid'
        res = pandas_processor.invoke({
            "data": perf_data if current_data is None else current_data, # Use current_data if already anchored
            "merge_data": budget_data,
            "merge_on": "plaid",
            "operation": "merge",
            "merge_how": "left"
        })
        
        if res.get("status") == "success":
            current_data = res.get("data")
            print("DEBUG [Reporter] Hybrid Merge Successful. Joined Budget to Performance.")
            
    # [NEW] Hybrid Merge Strategy (Unified Performance + Campaign Basic)
    # This connects ClickHouse Performance (cmpid) with MySQL Basic Info (campaign_id)
    # Useful when Group By is 'campaign_name' or 'cmpid'
    if "query_unified_performance" in data_store and "query_campaign_basic" in data_store:
        # Only if we haven't merged media_placements (which already brings in campaign info usually)
        if "query_media_placements" not in data_store:
            # [FIX] Check if anchor has 'cmpid' before merging
            if current_data and "cmpid" in current_data[0]:
                print("DEBUG [Reporter] Executing Hybrid Merge (Performance + Campaign Basic)...")
                basic_data = data_store["query_campaign_basic"]
                
                # Alias MySQL 'campaign_id' to ClickHouse 'cmpid'
                for row in basic_data:
                    if "campaign_id" in row:
                        row["cmpid"] = row["campaign_id"]
                
                res = pandas_processor.invoke({
                    "data": current_data,
                    "merge_data": basic_data,
                    "merge_on": "cmpid",
                    "operation": "merge",
                    "merge_how": "left"
                })
                
                if res.get("status") == "success":
                    current_data = res.get("data")
                    print("DEBUG [Reporter] Hybrid Merge (Campaign Level) Successful.")
            else:
                print("DEBUG [Reporter] Skipping Campaign Basic Merge: 'cmpid' not found in anchor table.")

    # [REORDER] Merge Ad Formats FIRST (Step 3 -> Step 4)
    if "query_ad_formats" in data_store:
        # [FIX] Check if merge key 'campaign_id' exists in anchor
        if current_data and "campaign_id" in current_data[0]:
            print("DEBUG [Reporter] Merging Ad Formats (Priority)...")
            # Use simple Campaign ID merge first to enrich the table with IDs
            res = pandas_processor.invoke({
                "data": current_data,
                "merge_data": data_store["query_ad_formats"],
                "merge_on": "campaign_id", 
                "operation": "merge",
                "merge_how": "left"
            })
            if res.get("status") == "success":
                current_data = res.get("data")
                print("DEBUG [Reporter] Ad Formats merged. Now we have dual IDs.")
        else:
            print("DEBUG [Reporter] Skipping Ad Formats Merge: 'campaign_id' not found in anchor table.")

    # [REORDER] Merge Performance SECOND (Step 4 -> Step 3)
    if "query_unified_performance" in data_store and current_data != data_store["query_unified_performance"]:
        print("DEBUG [Reporter] Merging Unified Performance (Dual-Path)...")
        perf_data = data_store["query_unified_performance"]
        
        # 1. Align IDs
        if perf_data:
            for row in perf_data:
                if "ad_format_type_id" in row:
                    row["format_type_id_exec"] = row["ad_format_type_id"] # Unified uses ad_format_type_id
                if "cmpid" in row:
                    row["campaign_id"] = row["cmpid"]
        
        # Check match rate with Execution ID
        def get_match_rate(left_data, right_data, on_keys):
            try:
                l_df = pd.DataFrame(left_data)
                r_df = pd.DataFrame(right_data)
                merged = pd.merge(l_df, r_df, on=on_keys, how="inner")
                return len(merged) / len(l_df) if len(l_df) > 0 else 0
            except:
                return 0

        # Try ID Match (Exec ID)
        match_rate = get_match_rate(current_data, perf_data, ["campaign_id", "format_type_id_exec"])
        print(f"DEBUG [Reporter] Strategy A (Exec ID Match) Rate: {match_rate:.2%}")
        
        final_merge_key = "campaign_id" # Default fallback
        
        if match_rate > 0.3:
            final_merge_key = "campaign_id, format_type_id_exec"
        else:
            # Fallback: Name Match (as backup)
            print("DEBUG [Reporter] Exec ID Match failed. Trying Strategy B (Name Match)...")
            def normalize_format(name):
                if not isinstance(name, str): return str(name)
                return name.replace("（已退役）", "").replace("(已退役)", "").replace("已退役 - ", "").strip().lower()
            
            for row in current_data:
                row["_norm_fmt"] = normalize_format(row.get("format_name", ""))
            for row in perf_data:
                # Unified performance usually has 'ad_format_type' as name
                fmt_name = row.get("ad_format_type") or row.get("format_name", "")
                row["_norm_fmt"] = normalize_format(fmt_name)
                
            name_match_rate = get_match_rate(current_data, perf_data, ["campaign_id", "_norm_fmt"])
            print(f"DEBUG [Reporter] Strategy B (Name Match) Rate: {name_match_rate:.2%}")
            
            if name_match_rate > 0:
                final_merge_key = "campaign_id, _norm_fmt"
            else:
                 # Final Fallback: Aggregation
                 print("DEBUG [Reporter] Fallback to Campaign Aggregation")
                 agg_res = pandas_processor.invoke({
                     "data": perf_data,
                     "operation": "groupby_sum",
                     "groupby_col": "campaign_id",
                     "sum_col": "effective_impressions, clicks, total_q100_views, total_engagements", # Updated for Unified cols
                     "sort_col": "campaign_id"
                 })
                 if agg_res.get("status") == "success":
                     perf_data = agg_res.get("data")
                     final_merge_key = "campaign_id"

        # Merge
        res = pandas_processor.invoke({
            "data": current_data,
            "merge_data": perf_data,
            "merge_on": final_merge_key,
            "operation": "merge",
            "merge_how": "left"
        })
        if res.get("status") == "success":
            current_data = res.get("data")
            # Cleanup
            if current_data and "_norm_fmt" in current_data[0]:
                for row in current_data:
                    row.pop("_norm_fmt", None)

    # 5. LLM Schema Planning (The Brain)
    # Instead of guessing, we ask the LLM to map columns based on user intent.
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
        except Exception as e:
            print(f"WARN [Reporter] Failed to load column_mapping.json: {e}")
            std_dict_str = "(Configuration Load Failed)"
            expansion_str = "(Configuration Load Failed)"

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

        **3. 欄位排序規則 (Column Ordering)**:
        請按照以下順序排列 `display_columns`：
        1. **主鍵** (Primary Key): 通常是「廣告格式」或「活動名稱」
        2. **文字型欄位** (Text Fields): 如「受眾標籤」「活動名稱」等描述性欄位
        3. **數值型欄位** (Numeric Fields): 如「投資金額」「點擊率 (CTR%)」等數字指標

        範例順序: ["廣告格式", "受眾標籤", "投資金額", "點擊率 (CTR%)", "觀看率 (VTR%)", "互動率 (ER%)"]

        **4. Top-N 排名識別 (Ranking & Limit)**:
        ⚠️ **重要**: 只有在使用者**明確要求排名**時才設定 `limit`，否則請設為 0（顯示全部）。

        - **需要設定 limit 的情況** (使用者明確要求排名):
          - **關鍵字**: 「前 X」「前X名」「前X大」「Top X」「排名前X」「最高X個」「最佳X個」
            - 例如：「前三大格式」→ limit=3
            - 例如：「Top 5 客戶」→ limit=5
            - 例如：「排名前十的活動」→ limit=10

        - **不需要設定 limit 的情況** (設為 0，顯示全部):
          - 使用者只是要「匯總」「統計」「分析」「所有」「各個」等，沒有明確要求排名
            - 例如：「代理商 YTD 認列金額」→ limit=0（顯示所有代理商）
            - 例如：「各產業的投資金額」→ limit=0（顯示所有產業）
            - 例如：「客戶的成效分析」→ limit=0（顯示所有客戶）

        **排序欄位選擇邏輯**：
        - 如果查詢提到「成效」且資料中有 CTR/VTR/ER，優先使用 `ctr`（點擊率）降序排列
        - 如果查詢提到「投資」「認列」「預算」「金額」，使用 `execution_amount` 或 `investment_amount` 降序排列
        - 如果查詢提到「曝光」，使用 `effective_impressions` 降序排列
        - 如果無法判斷，使用第一個數值型欄位降序排列

        ⚠️ **注意**: `sort_col` 必須使用**原始英文欄位名**（如 "ctr"、"execution_amount"），並在欄位名後加上 " DESC" 表示降序（例如 "execution_amount DESC"）

        - **⚠️ 特殊情況: 每組內排名 (Group-wise Top N)**:
          - **關鍵字**: 「各XX的 Top Y」「每個XX的前Y」
            - 例如：「各格式的 top5 客戶」→ 使用 `use_groupby_top_n=true`
            - 例如：「每個代理商的前3大客戶」→ 使用 `use_groupby_top_n=true`
          - **判斷邏輯**:
            - 查詢包含**兩個維度** (如「格式」+「客戶」)
            - 要求在**第一維度內**對**第二維度**排名
          - **處理方式**:
            - 設定 `use_groupby_top_n=true`
            - `groupby_cols` 只包含第一維度 (如 ["format_name"])
            - `limit` 設為每組要取的數量
            - 系統會自動使用特殊的 groupby_top_n 操作

        **5. 時間維度聚合 (Time Period Aggregation)**:
        如果使用者查詢包含以下時間聚合關鍵字，請設定 `time_aggregation`：
        - **關鍵字**: 「每月」「按月」「月報」「每季」「按季」「季報」「每年」「按年」「年報」
          - 例如：「每月預算」→ time_aggregation={{"enabled": true, "period": "month"}}
          - 例如：「按季度成效」→ time_aggregation={{"enabled": true, "period": "quarter"}}
          - 例如：「年度投資」→ time_aggregation={{"enabled": true, "period": "year"}}

        **時間聚合規則**：
        - 如果啟用時間聚合，系統會自動：
          1. 從可用的日期欄位 (自動偵測 "investment_start_date", "start_date", "end_date" 等) 生成時間維度欄位（如 "year_month"）
          2. 將時間維度欄位添加到 `groupby_cols` 的**第一位**
          3. 將時間維度中文名稱（如「年/月」）添加到 `display_columns` 的**第一位**
        - `period` 可選值: "month" (月), "quarter" (季), "year" (年)
        - 系統會自動選擇適當的日期欄位，你不需要指定 `source_col`

        ⚠️ **注意**: 時間維度欄位會自動生成，你不需要在 `rename_map` 中手動添加。

        **6. 佔比計算 (Percentage Calculation)**:
        如果使用者查詢包含以下佔比關鍵字，請設定 `percentage_config`：
        - **關鍵字**: 「佔比」「百分比」「比例」「percentage」「proportion」「share」「占比」
          - 例如：「各格式的預算佔比」→ percentage_config={{"enabled": true, "value_col": "investment_amount", "percentage_col": "佔比 (%)"}}
          - 例如：「客戶投資金額比例」→ percentage_config={{"enabled": true, "value_col": "investment_amount", "percentage_col": "比例 (%)"}}
          - 例如：「成效佔比」→ percentage_config={{"enabled": true, "value_col": "effective_impressions", "percentage_col": "佔比 (%)"}}

        **佔比計算規則**：
        - **value_col**: 要計算佔比的欄位（原始英文欄位名），通常是使用者查詢中提到的金額或數量欄位
          - 如果查詢提到「預算」「金額」「投資」，使用 "investment_amount" 或 "execution_amount"
          - 如果查詢提到「曝光」，使用 "effective_impressions"
          - 如果查詢提到「點擊」，使用 "total_clicks"
        - **percentage_col**: 佔比欄位的中文名稱（顯示用），建議使用「佔比 (%)」
        - 系統會自動：
          1. 計算每行 value_col 佔總和的百分比
          2. 將百分比欄位添加到 `display_columns` 的**最後一位**
          3. 將百分比欄位添加到 `rename_map` (如果需要)

        ⚠️ **重要**: 佔比計算會在 groupby_sum 之後執行，確保先完成數據聚合再計算佔比。

        **7. 聚合邏輯 (Aggregation Logic)**:
        - **`groupby_cols`**: 用於去重的維度欄位 (⚠️ **必須使用原始英文欄位名**)。
          - 例如，如果使用者查詢「各格式的產業分佈」，你應該設定 `groupby_cols=["format_name"]`。
        - **`sum_cols`**: 用於加總的指標欄位 (⚠️ **必須使用原始英文欄位名**)。
        - **`concat_col`**: **(新功能)** 用於字串聚合的欄位。
          - 當你將 `groupby_cols` 設為 `["format_name"]` 時，你應該同時設定 `concat_col="dimension_name"`，這樣系統就會自動將所有產業名稱合併成一個欄位。
          - **注意**: 系統假設輸入數據在 (groupby_col, concat_col) 組合上是唯一的，這通常由上游 SQL 保證。

        **8. 輸出要求**:
        - **rename_map**: 原始欄位 -> 標準中文名稱（用於最終顯示）。
        - **display_columns**: 最終要顯示的欄位列表（使用中文名稱）。
          - **規則**: 顯示主鍵 + 使用者明確要求的欄位 + 概念展開的欄位。
          - **禁止**: 嚴禁出現「客戶名稱」「代理商」「活動編號」「cmpid」「plaid」「format_type_id」等內部欄位，除非使用者明確詢問。
          - **嚴格過濾**: 只有在使用者明確要求（或概念展開需要）時才顯示「廣告格式」。如果使用者問「成效」，通常只需要「活動名稱」搭配成效指標即可。
        - **groupby_cols**: 根據上述聚合邏輯設定 (英文名)。
        - **concat_col**: 根據上述聚合邏輯設定 (英文名)。
        - **sum_cols**: 用於加總的指標欄位 (英文名)。
        - **sort_col**: 排序欄位（原始英文欄位名 + " DESC" 或 " ASC"）。
          - 如果有聚合 (groupby)，請務必使用加總後的欄位（如 "total_budget DESC"）進行排序，以顯示正確的排名。
          - 如果不需要排序則留空 ""。
        - **limit**: 限制顯示筆數（整數）。如果使用者要「前X」則設為 X，否則設為 0。
        - **time_aggregation**: 時間聚合配置。
        - **percentage_config**: 佔比計算配置。

        ⚠️ **重要**: `groupby_cols`, `sum_cols`, `concat_col`, `sort_col` 等都使用原始英文欄位名, `display_columns` 使用中文名。

        請直接回傳 JSON 格式，不要包含任何 Markdown 標記或文字說明。
        範例格式: {{"rename_map": {{}}, "display_columns": [], "sort_col": "", "groupby_cols": [], "sum_cols": [], "concat_col": "", "limit": 0, ...}}
        """
        
        try:
            # Use a simpler LLM call for JSON planning
            plan_response = llm.invoke([
                SystemMessage(content="You are a JSON generator. Output only valid raw JSON without any markdown formatting."),
                HumanMessage(content=SCHEMA_PROMPT)
            ])
            content = plan_response.content
            if isinstance(content, list): content = " ".join([c.get("text", "") for c in content])
            
            # Extract JSON and clean up
            content = content.replace("```json", "").replace("```", "").strip()
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                plan_json = json_match.group(0)
                plan = json.loads(plan_json)
                
                # --- [NEW] Schema Plan Optimizer (Rule-Based Overrides) ---
                # Rule 1: Auto-Aggregate Industry by Format
                # If the planner tries to group by BOTH format and industry, it creates granular rows.
                # We want to group by Format and CONCAT Industry for a cleaner report.
                raw_groupby = plan.get("groupby_cols", [])
                
                # Check for Format + Industry combination
                has_format = "format_name" in raw_groupby
                has_dimension = "dimension_name" in raw_groupby
                
                if has_format and has_dimension:
                    print(f"DEBUG [Reporter] Plan Optimizer: Detected granular Format+Industry grouping. Switching to Aggregation.")
                    
                    # Remove dimension_name from groupby
                    plan["groupby_cols"] = [col for col in raw_groupby if col != "dimension_name"]
                    
                    # Set concat_col to dimension_name
                    plan["concat_col"] = "dimension_name"
                    
                    # Ensure dimension_name is NOT in sum_cols (just in case)
                    if "sum_cols" in plan:
                        plan["sum_cols"] = [col for col in plan["sum_cols"] if col != "dimension_name"]

                print(f"DEBUG [Reporter] Schema Plan Success: {plan}")

                # [NEW] Auto-convert Chinese column names to English for groupby/sum operations
                # Build reverse mapping: Chinese -> English
                reverse_map = {v: k for k, v in plan.get("rename_map", {}).items()}

                # Convert groupby_cols
                groupby_cols_en = []
                for col in plan.get("groupby_cols", []):
                    # If it's Chinese, convert to English; otherwise keep as is
                    groupby_cols_en.append(reverse_map.get(col, col))
                
                # Convert concat_col
                concat_col_en = plan.get("concat_col", "")
                if concat_col_en in reverse_map:
                    concat_col_en = reverse_map[concat_col_en]

                # Convert sum_cols
                sum_cols_en = []
                for col in plan.get("sum_cols", []):
                    sum_cols_en.append(reverse_map.get(col, col))

                # [NEW] Auto-inject Performance Raw Metrics into sum_cols
                # If the plan requests Rate metrics (CTR/VTR/ER) but forgets Raw metrics (Impressions/Clicks),
                # pandas_processor cannot calculate the weighted average rate.
                # We must ensure raw metrics are present in the aggregation.
                rate_metrics = ["ctr", "vtr", "er"]
                raw_metrics_map = {
                    "ctr": ["effective_impressions", "total_impressions", "total_clicks"],
                    "vtr": ["total_q100_views", "total_q100", "effective_impressions", "total_impressions"], # Simplified VTR calc
                    "er": ["total_engagements", "effective_impressions", "total_impressions"]
                }
                
                # Check if any rate metric is in display_columns (mapped to Chinese) or sum_cols (English)
                # Display columns are in Chinese, map back to English
                requested_cols_en = []
                for col_cn in plan.get("display_columns", []):
                    requested_cols_en.append(reverse_map.get(col_cn, col_cn))
                
                # Also check sort_col
                sort_col_raw = plan.get("sort_col", "").split(" ")[0]
                if sort_col_raw: requested_cols_en.append(sort_col_raw)

                for rate in rate_metrics:
                    # If rate is requested (either in display or sort)
                    if any(rate in col.lower() for col in requested_cols_en):
                        raws = raw_metrics_map.get(rate, [])
                        for raw in raws:
                            if raw not in sum_cols_en:
                                # Only add if it exists in the dataframe
                                if raw in available_cols:
                                    sum_cols_en.append(raw)
                                    print(f"DEBUG [Reporter] Auto-injected '{raw}' into sum_cols for {rate} calculation")

                print(f"DEBUG [Reporter] Converted groupby_cols: {plan.get('groupby_cols', [])} -> {groupby_cols_en}")
                print(f"DEBUG [Reporter] Converted concat_col: {plan.get('concat_col', '')} -> {concat_col_en}")
                print(f"DEBUG [Reporter] Converted sum_cols: {plan.get('sum_cols', [])} -> {sum_cols_en}")

                # [NEW] Handle Time Aggregation
                time_agg = plan.get("time_aggregation", {"enabled": False})
                if time_agg.get("enabled"):
                    period = time_agg.get("period", "month")

                    # Auto-detect available date column
                    date_candidates = ["investment_start_date", "start_date", "campaign_start_date", "end_date"]
                    source_col = None
                    for col in date_candidates:
                        if col in available_cols:
                            source_col = col
                            break

                    if not source_col:
                        print(f"WARNING [Reporter] Time aggregation enabled but no date column found. Skipping.")
                        time_agg["enabled"] = False
                    else:
                        # Determine period column name
                        if period == "month":
                            period_col_en = "year_month"
                            period_col_cn = "年/月"
                        elif period == "quarter":
                            period_col_en = "year_quarter"
                            period_col_cn = "年/季"
                        elif period == "year":
                            period_col_en = "year"
                            period_col_cn = "年份"
                        else:
                            period_col_en = "year_month"
                            period_col_cn = "年/月"

                        print(f"DEBUG [Reporter] Time aggregation enabled: period={period}, source={source_col}")

                        # Execute add_time_period operation
                        current_data = pandas_processor.invoke({
                            "data": current_data,
                            "operation": "add_time_period",
                            "date_col": source_col,
                            "new_col": period_col_en,
                            "period": period
                        }).get("data", [])

                        # Add time column to groupby_cols (first position)
                        groupby_cols_en.insert(0, period_col_en)

                        # Add time column to display_columns (first position)
                        display_columns = plan.get("display_columns", [])
                        if period_col_cn not in display_columns:
                            display_columns.insert(0, period_col_cn)
                            plan["display_columns"] = display_columns

                        # Add time column to rename_map
                        rename_map = plan.get("rename_map", {})
                        rename_map[period_col_en] = period_col_cn
                        plan["rename_map"] = rename_map

                        print(f"DEBUG [Reporter] Added time column: {period_col_en} -> {period_col_cn}")

                # Execute Plan
                # Determine top_n from Schema Plan's limit parameter
                limit = plan.get("limit", 0)

                # Smart top_n logic:
                # 1. If user explicitly wants top N (limit > 0), use it
                # 2. If dataset is small (<= 50 rows), show all
                # 3. Otherwise, show 100 rows
                data_size = len(current_data)
                if limit > 0:
                    top_n = limit
                elif data_size <= 50:
                    top_n = data_size  # Show all for small datasets
                else:
                    top_n = 100  # Default cap for large datasets

                print(f"DEBUG [Reporter] Display logic: data_size={data_size}, limit={limit}, top_n={top_n}")

                # [NEW] Handle Percentage Calculation - Check BEFORE groupby_sum
                percentage_config = plan.get("percentage_config", {"enabled": False})
                needs_percentage = percentage_config.get("enabled", False)

                if needs_percentage:
                    # Step 1: Aggregate WITHOUT truncation to get correct total
                    print(f"DEBUG [Reporter] Percentage mode: Aggregating first (keeping English column names)")
                    aggregated_result = pandas_processor.invoke({
                        "data": current_data,
                        "operation": "groupby_sum",
                        "groupby_col": ",".join(groupby_cols_en),
                        "sum_col": ",".join(sum_cols_en),
                        "concat_col": concat_col_en,
                        "sort_col": plan.get("sort_col"),
                        "ascending": False,
                        "top_n": 0  # CRITICAL FIX: Must encompass ALL rows for correct denominator
                    })

                    if aggregated_result.get("status") == "success":
                        # Step 2: Calculate percentage (Denominator = Sum of all rows)
                        value_col = percentage_config.get("value_col")
                        percentage_col_cn = percentage_config.get("percentage_col", "佔比 (%)")

                        print(f"DEBUG [Reporter] Adding percentage column based on '{value_col}'")
                        percentage_result = pandas_processor.invoke({
                            "data": aggregated_result.get("data", []),
                            "operation": "add_percentage_column",
                            "sum_col": value_col,
                            "new_col": "percentage"
                        })

                        if percentage_result.get("status") == "success":
                            # Step 3: Apply rename_map, select_columns AND TRUNCATION
                            rename_map = plan.get("rename_map", {})
                            rename_map["percentage"] = percentage_col_cn

                            display_columns = plan.get("display_columns", [])
                            if percentage_col_cn not in display_columns:
                                display_columns.append(percentage_col_cn)

                            print(f"DEBUG [Reporter] Applying rename and select with percentage column")
                            final_result = pandas_processor.invoke({
                                "data": percentage_result.get("data", []),
                                "operation": "groupby_sum", # Just for rename/select/sort/limit
                                "rename_map": rename_map,
                                "groupby_col": ",".join(groupby_cols_en),
                                "sum_col": ",".join(sum_cols_en) + ",percentage",
                                "concat_col": concat_col_en,
                                "select_columns": display_columns,
                                "sort_col": plan.get("sort_col"),
                                "ascending": False,
                                "top_n": top_n # NOW we apply the limit
                            })
                        else:
                            print(f"WARN [Reporter] Percentage calculation failed: {percentage_result.get('markdown', 'Unknown error')}")
                            # Fallback: use aggregated result without percentage
                            final_result = aggregated_result
                    else:
                        # Aggregation failed
                        final_result = aggregated_result
                else:
                    # [NEW] Check if this is a group-wise top N scenario
                    use_groupby_top_n = plan.get("use_groupby_top_n", False)

                    if use_groupby_top_n:
                        print(f"DEBUG [Reporter] Detected group-wise top N query. Using special aggregation...")

                        # Step 1: Aggregate first (按 format + client 聚合)
                        all_groupby_cols = groupby_cols_en.copy()
                        # Need to include the second dimension (client) in groupby
                        # Extract from display_columns: find client-like columns
                        client_col_candidates = ["client_name", "advertiser_name", "brand", "company"]
                        client_col = None
                        for col in client_col_candidates:
                            if col in available_cols:
                                client_col = col
                                break

                        if client_col and client_col not in all_groupby_cols:
                            all_groupby_cols.append(client_col)

                        print(f"DEBUG [Reporter] Group-wise aggregation columns: {all_groupby_cols}")

                        aggregated_result = pandas_processor.invoke({
                            "data": current_data,
                            "operation": "groupby_sum",
                            "groupby_col": ",".join(all_groupby_cols),
                            "sum_col": ",".join(sum_cols_en),
                            "concat_col": concat_col_en,
                            "sort_col": plan.get("sort_col"),
                            "ascending": False,
                            "top_n": 0  # No limit yet
                        })

                        if aggregated_result.get("status") == "success":
                            # Step 2: Apply groupby_top_n
                            final_result = pandas_processor.invoke({
                                "data": aggregated_result.get("data", []),
                                "operation": "groupby_top_n",
                                "rename_map": plan.get("rename_map", {}),
                                "groupby_col": ",".join(groupby_cols_en),  # Only the first dimension
                                "sort_col": plan.get("sort_col"),
                                "top_n": top_n,
                                "select_columns": plan.get("display_columns", [])
                            })
                        else:
                            final_result = aggregated_result
                    else:
                        # No percentage, no group-wise top N - standard flow with rename
                        final_result = pandas_processor.invoke({
                            "data": current_data,
                            "operation": "groupby_sum",
                            "rename_map": plan.get("rename_map", {}),
                            "groupby_col": ",".join(groupby_cols_en),
                            "sum_col": ",".join(sum_cols_en),
                            "concat_col": concat_col_en,
                            "select_columns": plan.get("display_columns", []),
                            "sort_col": plan.get("sort_col"),
                            "ascending": False,
                            "top_n": top_n
                        })

            else:
                raise ValueError("No valid JSON found in LLM response")

        except Exception as e:
            print(f"DEBUG [Reporter] Planning failed ({e}). Attempting best-effort fallback.")
            # Fallback: 只顯示關鍵欄位，避開 ID
            fallback_select = [c for c in available_cols if not c.lower().endswith('id')]
            final_result = pandas_processor.invoke({
                "data": current_data,
                "operation": "top_n", 
                "top_n": 100,
                "select_columns": fallback_select[:7], # 限制數量
                "sort_col": available_cols[0]
            })
    else:
        final_result = {"markdown": ""}

    final_table = final_result.get("markdown", "")
    
    # --- LLM Summary Generation ---
    # Now we ask LLM to summarize based on the table we generated
    
    # [NEW] Extract dates for the prompt
    routing_context = state.get("routing_context", {})
    start_date = routing_context.get("start_date", "指定期間")
    end_date = routing_context.get("end_date", "指定期間")
    
    SUMMARY_PROMPT = """
    你是數據報告呈現者。請針對使用者查詢「{query}」與生成的數據表產出回應。
    
    請回傳 JSON 格式，包含以下欄位：
    1. "suggestions": 根據數據結果，提供 3 個具體且高度相關的後續查詢建議（帶有 💡 符號與標題，例如：💡 **您還可以嘗試查詢：** ...）。
    
    **規則**:
    - **嚴禁分析**: 不要在輸出中包含任何數據解讀或總結。
    - **JSON 格式**: 只回傳原始 JSON，不要包含 Markdown 標記。
    """
    
    # [FIX] Programmatically generate opening to ensure date accuracy
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
                # opening_text is already set programmatically
                suggestions_data = res_json.get("suggestions", "")
                
                if isinstance(suggestions_data, list):
                    suggestions_text = "\n".join(suggestions_data)
                else:
                    suggestions_text = str(suggestions_data)
                
                # [NEW] Sanitize suggestions_text specifically
                suggestions_text = suggestions_text.strip()
                if suggestions_text.startswith("```"):
                    suggestions_text = re.sub(r"^```[a-zA-Z]*\n?", "", suggestions_text)
                    suggestions_text = re.sub(r"\n?```$", "", suggestions_text)
                suggestions_text = suggestions_text.strip()
            else:
                print(f"DEBUG [Reporter] JSON not found in summary response.")
        except Exception as e:
            print(f"DEBUG [Reporter] Summary JSON parsing failed: {e}")
    else:
        opening_text = "抱歉，無法從數據中生成報表。"

    # Final Assembly (Correct Order: Opening -> Table -> Suggestions)
    final_response = opening_text + "\n\n" + final_table
    if suggestions_text:
        final_response += "\n\n" + suggestions_text

    # --- [NEW] Robust Sanitization ---
    # This prevents the UI from rendering the entire report as a raw code block
    print(f"DEBUG [Reporter] Pre-sanitization response length: {len(final_response)}")
    print(f"DEBUG [Reporter] Pre-sanitization start: {final_response[:50]!r}")
    
    # 1. Strip leading/trailing whitespace
    final_response = final_response.strip()
    
    # 2. Force remove wrapping code blocks using string methods (more reliable than regex)
    if final_response.startswith("```"):
        # Find the first newline to identify the language tag line
        first_newline = final_response.find("\n")
        if first_newline != -1:
            # Check if the first line is just ``` or ```text etc.
            first_line = final_response[:first_newline].strip()
            # If it starts with ```, we assume it's a code block header
            print(f"DEBUG [Reporter] Removing start block header: {first_line!r}")
            final_response = final_response[first_newline+1:]
        else:
             # Single line case, just remove the backticks
             final_response = final_response.replace("```", "")

    # Remove end block
    if final_response.endswith("```"):
        print("DEBUG [Reporter] Removing end block footer")
        final_response = final_response[:-3].strip()
    
    final_response = final_response.strip()
    print(f"DEBUG [Reporter] Post-sanitization response length: {len(final_response)}")
    print(f"DEBUG [Reporter] Post-sanitization start: {final_response[:50]!r}")

    return {
        "final_response": final_response,
        "messages": [AIMessage(content=final_response)],
        "debug_logs": execution_logs
    }
