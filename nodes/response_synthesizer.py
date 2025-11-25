from langchain_core.messages import AIMessage
from prompts.response_synthesizer_prompt import RESPONSE_SYNTHESIZER_PROMPT
from config.llm import llm
from schemas.state import AgentState
from typing import Dict, Any
import pandas as pd
import numpy as np


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
    
    if 'total_clicks' in df.columns and 'effective_impressions' in df.columns and pd.to_numeric(df['total_clicks'], errors='coerce').notna().any() and pd.to_numeric(df['effective_impressions'], errors='coerce').notna().any():
        total_clicks = pd.to_numeric(df['total_clicks'], errors='coerce').sum()
        total_imps = pd.to_numeric(df['effective_impressions'], errors='coerce').sum()
        # 重新計算整體的 CTR，而不是對個別 CTR 取平均 (那是錯誤的數學)
        insights['avg_ctr'] = (total_clicks / total_imps * 100) if total_imps > 0 else 0

    if 'Budget_Sum' in df.columns and 'total_clicks' in df.columns and pd.to_numeric(df['Budget_Sum'], errors='coerce').notna().any() and pd.to_numeric(df['total_clicks'], errors='coerce').notna().any():
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

    # 3. 異常偵測 (Anomalies)
    # 例如：有花錢但沒點擊
    if 'Budget_Sum' in df.columns and 'total_clicks' in df.columns and pd.to_numeric(df['Budget_Sum'], errors='coerce').notna().any() and pd.to_numeric(df['total_clicks'], errors='coerce').notna().any():
        wasted_spend_df = df[(pd.to_numeric(df['Budget_Sum'], errors='coerce') > 0) & (pd.to_numeric(df['total_clicks'], errors='coerce') == 0)]
        if not wasted_spend_df.empty:
            insights['wasted_budget_campaigns'] = len(wasted_spend_df)

    return insights


def response_synthesizer_node(state: AgentState) -> Dict[str, Any]:
    """
    Synthesizes a response by first calculating statistical insights from the data,
    then feeding both the data and the insights into an LLM to generate a
    natural language report with actionable suggestions.
    """
    # 1. 獲取資料並建立 DataFrame
    final_dataframe = state.get("final_dataframe")
    
    if final_dataframe is None or len(final_dataframe) == 0:
        # Fallback to sql_result if final_dataframe is not available
        sql_result = state.get("sql_result")
        sql_result_columns = state.get("sql_result_columns")
        if not sql_result or not sql_result_columns:
            return {"messages": [AIMessage(content="查無資料，請嘗試調整您的查詢條件。")]}
        df = pd.DataFrame(sql_result, columns=sql_result_columns)
    else:
        df = pd.DataFrame(final_dataframe)

    if state.get("error_message"):
        return {"messages": [AIMessage(content=f"抱歉，執行查詢時發生錯誤：{state['error_message']}")]}

    if df.empty:
        return {"messages": [AIMessage(content="查無資料，請嘗試調整您的查詢條件。")]}
    
    # 2. 預先計算統計摘要
    stats = calculate_insights(df)
    insights_summary = "\n".join([f"- {key}: {value:.2f}" if isinstance(value, (int, float)) else f"- {key}: {value}" for key, value in stats.items()])
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

    # 5. 呼叫 LLM 生成最終分析報告
    prompt = RESPONSE_SYNTHESIZER_PROMPT.format(
        insights_summary=insights_summary,
        formatted_table_string=formatted_table_string
    )
    
    chain = llm
    response_text = chain.invoke(prompt).content
        
    # 6. 回傳最終訊息
    return {"messages": [AIMessage(content=response_text)]}