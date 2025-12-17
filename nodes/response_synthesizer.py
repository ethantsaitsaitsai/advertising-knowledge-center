from langchain_core.messages import AIMessage
from prompts.response_synthesizer_prompt import RESPONSE_SYNTHESIZER_PROMPT
from config.llm import llm
from config.registry import config
from schemas.state import AgentState
from typing import Dict, Any
import pandas as pd
from nodes.data_fusion import data_fusion_node  # Import Fusion Logic


def calculate_insights(df: pd.DataFrame) -> Dict[str, Any]:
    """
    使用 Python 計算絕對準確的統計數據，餵給 LLM 作為分析基礎。
    """
    if df.empty:
        return {}

    insights = {}

    # 1. 總體指標 (Aggregates)
    # 需確保欄位存在且為數值
    if 'Budget_Sum' in df.columns and pd.to_numeric(df['Budget_Sum'], errors='coerce').notna().any():
        # With granular SQL (pcd.budget), simple sum is correct for the result set.
        insights['total_budget'] = pd.to_numeric(df['Budget_Sum'], errors='coerce').sum()

    if (
        'total_clicks' in df.columns and
        'effective_impressions' in df.columns and
        pd.to_numeric(df['total_clicks'], errors='coerce').notna().any() and
        pd.to_numeric(df['effective_impressions'], errors='coerce').notna().any()
    ):
        total_clicks = pd.to_numeric(df['total_clicks'], errors='coerce').sum()
        total_imps = pd.to_numeric(df['effective_impressions'], errors='coerce').sum()
        # 重新計算整體的 CTR，而不是對個別 CTR 取平均 (那是錯誤的數學)
        insights['avg_ctr'] = (total_clicks / total_imps * 100) if total_imps > 0 else 0

    if (
        'Budget_Sum' in df.columns and
        'total_clicks' in df.columns and
        pd.to_numeric(df['Budget_Sum'], errors='coerce').notna().any() and
        pd.to_numeric(df['total_clicks'], errors='coerce').notna().any()
    ):
        total_budget = pd.to_numeric(df['Budget_Sum'], errors='coerce').sum()
        total_clicks = pd.to_numeric(df['total_clicks'], errors='coerce').sum()
        insights['avg_cpc'] = (total_budget / total_clicks) if total_clicks > 0 else 0

    # 2. 排行榜 (Top Performers) - 假設以 CTR 為例
    if 'CTR' in df.columns and pd.to_numeric(df['CTR'], errors='coerce').notna().any() and len(df) > 1:
        # Ensure CTR is numeric before finding idxmax
        df['CTR_numeric'] = pd.to_numeric(df['CTR'], errors='coerce')
        df_numeric = df.dropna(subset=['CTR_numeric'])
        if not df_numeric.empty:
            top_ctr_row = df_numeric.loc[df_numeric['CTR_numeric'].idxmax()]
            # 假設有名稱欄位，需依實際欄位調整
            name_col = next((col for col in df.columns if 'name' in col.lower() or '名稱' in col), 'cmpid')
            insights['top_performer_name'] = top_ctr_row.get(name_col, 'N/A')
            insights['top_performer_ctr'] = top_ctr_row.get('CTR_numeric', 0)
        
        # Clean up temporary column
        if 'CTR_numeric' in df.columns:
            df.drop(columns=['CTR_numeric'], inplace=True)


    # 3. 異常偵測 (Anomalies)
    # 例如：有花錢但沒點擊
    if (
        'Budget_Sum' in df.columns and
        'total_clicks' in df.columns and
        pd.to_numeric(df['Budget_Sum'], errors='coerce').notna().any() and
        pd.to_numeric(df['total_clicks'], errors='coerce').notna().any()
    ):
        wasted_spend_df = df[(pd.to_numeric(df['Budget_Sum'], errors='coerce') > 0) &
                             (pd.to_numeric(df['total_clicks'], errors='coerce') == 0)]
        if not wasted_spend_df.empty:
            insights['wasted_budget_campaigns'] = len(wasted_spend_df)

    return insights


def response_synthesizer_node(state: AgentState) -> Dict[str, Any]:
    """
    Synthesizes a response by first calculating statistical insights from the data,
    then feeding both the data and the insights into an LLM to generate a
    natural language report with actionable suggestions.
    """
    print(f"DEBUG [Synthesizer] State Keys: {list(state.keys())}")
    print(f"DEBUG [Synthesizer] Campaign Data Present: {bool(state.get('campaign_data'))}")

    # --- Check for Clarification Messages ---
    # If the last message is a clarification/question from CampaignAgent,
    # just pass it through without trying to synthesize data
    messages = state.get("messages", [])
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, "name") and last_message.name == "CampaignAgent":
            # This is a clarification or intermediate message from CampaignAgent
            # The message is already in the messages list, so we DON'T add it again
            # Just return empty update and set clarification_pending flag
            print(f"DEBUG [Synthesizer] Clarification message detected from CampaignAgent: {last_message.content[:100]}...")
            print("DEBUG [Synthesizer] Message already in list. Not adding again (prevents duplication).")
            return {
                "clarification_pending": True  # Mark that clarification is pending and waiting for user response
                # Note: NO "messages" key here - we don't want to add the message again!
            }

    # Also check if there's campaign_data but it's empty
    # In this case, CampaignAgent should have returned a clarification message
    # If it didn't make it to messages list, check the raw state
    campaign_data = state.get("campaign_data")
    if campaign_data and not campaign_data.get("data"):
        # Data exists but is empty - this shouldn't reach here if Router did its job
        # But just in case, ask for clarification instead of showing "No data"
        print("DEBUG [Synthesizer] Campaign data is empty. Asking for clarification.")
        return {
            "messages": [AIMessage(content=(
                "根據您的查詢條件，我暫時找不到相符的數據。\n\n"
                "這可能是因為：\n"
                "- 時間範圍內沒有相關數據\n"
                "- 實體名稱或條件組合不存在\n\n"
                "您想調整查詢條件或嘗試其他時間範圍嗎？"
            ))]
        }

    # --- Data Fusion Logic ---
    perf_data = state.get("final_dataframe") # From PerformanceAgent (ClickHouse)
    campaign_data = state.get("sql_result")  # From CampaignAgent (MySQL)

    # Fallback: Use campaign_data if sql_result is not available
    if not campaign_data and state.get("campaign_data"):
        campaign_data = state.get("campaign_data", {}).get("data")
    
    df = pd.DataFrame()
    
    # Unified Fusion Logic: Always use DataFusion for consistency (Sorting, Limiting, Formatting)
    if perf_data or campaign_data:
        print(f"DEBUG [Synthesizer] Data detected. Initiating Fusion.")
        
        # Temporarily inject 'clickhouse_result' into state for data_fusion_node if not present
        fusion_state = state.copy()
        if not fusion_state.get("clickhouse_result") and perf_data:
             fusion_state["clickhouse_result"] = perf_data
        
        fusion_result = data_fusion_node(fusion_state)
        fused_data = fusion_result.get("final_dataframe")
        
        if fused_data:
             df = pd.DataFrame(fused_data)
             print(f"DEBUG [Synthesizer] Fusion Complete. Rows: {len(df)}")
        else:
             print(f"DEBUG [Synthesizer] Fusion returned empty. Reason: {fusion_result.get('final_result_text')}")
             # Fallback: Try to use whatever raw data we have
             if perf_data: 
                 df = pd.DataFrame(perf_data)
             elif campaign_data: 
                 cols = state.get("sql_result_columns") or state.get("campaign_data", {}).get("columns")
                 df = pd.DataFrame(campaign_data, columns=cols) if cols else pd.DataFrame(campaign_data)
                 
             # Safety: Hide technical columns even in fallback
             hidden_cols = config.get_hidden_columns()
             if not df.empty:
                 print(f"DEBUG [Synthesizer] Applying Fallback Column Hiding: {hidden_cols}")
                 df = df.drop(columns=[c for c in df.columns if c.lower() in hidden_cols], errors='ignore')

    # -------------------------

    if state.get("error_message"):
        return {"messages": [AIMessage(content=f"抱歉，執行查詢時發生錯誤：{state['error_message']}")]}

    if df.empty:
        # If we reach here with empty data, it means CampaignAgent Router didn't catch it
        # This shouldn't happen with the new router logic, but provide helpful message
        print("DEBUG [Synthesizer] DataFrame is empty. Showing clarification message.")
        return {"messages": [AIMessage(content=(
            "根據您的查詢條件，我暫時找不到相符的數據。\n\n"
            "請嘗試：\n"
            "- 調整時間範圍（例如：查詢其他月份或年份）\n"
            "- 確認實體名稱是否正確\n"
            "- 嘗試查詢其他指標\n\n"
            "您想修改查詢條件嗎？"
        ))]}

    # 2. 預先計算統計摘要
    stats = calculate_insights(df)
    insights_summary = "\n".join([f"- {key}: {value:.2f}" if isinstance(value, (int, float))
                                  else f"- {key}: {value}" for key, value in stats.items()])
    
    budget_note = state.get("budget_note")
    if budget_note:
        insights_summary += f"\n- **Budget Note**: {budget_note}"

    if not insights_summary:
        insights_summary = "沒有足夠的數據來生成統計摘要。"

    # 3. 表格前處理
    # 3.1 重新排列欄位順序：將 start_date 和 end_date 移到 Campaign_Name 後面
    # Note: Zero-value metric filtering is handled in DataFusion (nodes/data_fusion.py)
    if 'Campaign_Name' in df.columns:
        cols = list(df.columns)
        # 找到 Campaign_Name 的位置
        campaign_idx = cols.index('Campaign_Name')

        # 移除 start_date 和 end_date（如果存在）
        date_cols = []
        for date_col in ['start_date', 'end_date']:
            if date_col in cols:
                date_cols.append(date_col)
                cols.remove(date_col)

        # 將日期欄位插入到 Campaign_Name 之後
        if date_cols:
            for i, date_col in enumerate(date_cols):
                cols.insert(campaign_idx + 1 + i, date_col)
            df = df[cols]
            print(f"DEBUG [Synthesizer] Reordered columns: {date_cols} moved after Campaign_Name")

    # 3.2 生成 Markdown 表格
    formatted_table_string = df.to_markdown(index=False, floatfmt=".2f")

    # 4. 【關鍵邏輯】動態添加 Limit 提示 (Smart Footer)
    DEFAULT_LIMIT = 20
    if len(df) == DEFAULT_LIMIT:
        footer_note = (
            f"\n\n---\n"
            f"💡 **顯示提示**：目前預設顯示前 **{DEFAULT_LIMIT}** 筆數據。\n"
            f"如果您需要更多資料（例如「看前 50 筆」或「全部」），請直接回覆告知，我會為您調整。"
        )
        formatted_table_string += footer_note

    # 4.1 Default Metrics Note
    was_default = state.get("was_default_metrics", False)
    if was_default:
        formatted_table_string += (
            f"\n\n---\n"
            f"💡 **預設指標提示**：因未指定特定指標，系統已自動為您抓取 **CTR, VTR, ER**。\n"
            f"若需要其他成效數據 (如 Impressions, Clicks)，請隨時告知。"
        )

    # 5. 呼叫 LLM 生成最終分析報告
    prompt = RESPONSE_SYNTHESIZER_PROMPT.format(
        insights_summary=insights_summary,
        formatted_table_string=formatted_table_string
    )

    chain = llm
    response_text = chain.invoke(prompt).content

    # 6. 回傳最終訊息
    return {"messages": [AIMessage(content=response_text)]}
