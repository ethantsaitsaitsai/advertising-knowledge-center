from langchain_core.messages import AIMessage
from prompts.response_synthesizer_prompt import RESPONSE_SYNTHESIZER_PROMPT
from config.llm import llm
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
    
    # --- Data Fusion Logic ---
    perf_data = state.get("final_dataframe") # From PerformanceAgent (ClickHouse)
    campaign_data = state.get("sql_result")  # From CampaignAgent (MySQL)
    
    df = pd.DataFrame()
    
    # Case 1: Heterogeneous Fusion (Both Sources Available)
    # In parallel mode, we might have both. We want to merge them.
    if perf_data and campaign_data:
        print(f"DEBUG [Synthesizer] Both Performance and Campaign data detected. Initiating Fusion.")
        print(f"DEBUG [Synthesizer] Perf Data: {len(perf_data)} rows.")
        print(f"DEBUG [Synthesizer] Campaign Data: {len(campaign_data)} rows.")
        
        # Check if we have columns
        sql_cols = state.get("sql_result_columns")
        print(f"DEBUG [Synthesizer] SQL Columns: {sql_cols}")
        
        # Temporarily inject 'clickhouse_result' into state for data_fusion_node if not present
        # data_fusion_node expects 'clickhouse_result' but PerformanceAgent outputs 'final_dataframe'
        # Let's align them.
        fusion_state = state.copy()
        if not fusion_state.get("clickhouse_result"):
             fusion_state["clickhouse_result"] = perf_data
        
        fusion_result = data_fusion_node(fusion_state)
        fused_data = fusion_result.get("final_dataframe")
        
        if fused_data:
             df = pd.DataFrame(fused_data)
             print(f"DEBUG [Synthesizer] Fusion Complete. Rows: {len(df)}")
        else:
             print(f"DEBUG [Synthesizer] Fusion returned empty. Reason: {fusion_result.get('final_result_text')}")
             df = pd.DataFrame(perf_data)

    # Case 2: Only Performance Data (Legacy or cached)
    elif perf_data:
        print("DEBUG [Synthesizer] Only Performance data detected.")
        df = pd.DataFrame(perf_data)
        
    # Case 3: Only Campaign Data (Metadata query)
    elif campaign_data:
        print("DEBUG [Synthesizer] Only Campaign data detected.")
        sql_result_columns = state.get("sql_result_columns")
        if sql_result_columns:
            df = pd.DataFrame(campaign_data, columns=sql_result_columns)
        else:
            df = pd.DataFrame(campaign_data)

    # -------------------------

    if state.get("error_message"):
        return {"messages": [AIMessage(content=f"抱歉，執行查詢時發生錯誤：{state['error_message']}")]}

    if df.empty:
        return {"messages": [AIMessage(content=f"查無資料，請嘗試調整您的查詢條件。")]}

    # 2. 預先計算統計摘要
    stats = calculate_insights(df)
    insights_summary = "\n".join([f"- {key}: {value:.2f}" if isinstance(value, (int, float))
                                  else f"- {key}: {value}" for key, value in stats.items()])
    
    budget_note = state.get("budget_note")
    if budget_note:
        insights_summary += f"\n- **Budget Note**: {budget_note}"

    if not insights_summary:
        insights_summary = "沒有足夠的數據來生成統計摘要。"

    # 3. 生成 Markdown 表格
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
