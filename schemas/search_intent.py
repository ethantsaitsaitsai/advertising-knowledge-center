from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class DateRange(BaseModel):
    """明確的時間區間物件，避免 List 索引錯誤"""
    start: Optional[str] = Field(None, description="開始日期 YYYY-MM-DD")
    end: Optional[str] = Field(None, description="結束日期 YYYY-MM-DD")


class AnalysisNeeds(BaseModel):
    """詳細定義分析需求"""

    # 定義更精確的指標 Enum，強迫 LLM 做選擇
    metrics: List[Literal[
        "Budget_Sum",       # 預算總和 (媒體預算)
        "AdPrice_Sum",      # 實際花費總和 (廣告賣價)
        "Insertion_Count",  # 委刊單數量 (COUNT id)
        "Campaign_Count"    # 案件數量 (COUNT DISTINCT)
    ]] = Field(default_factory=list, description="要計算的數值指標")

    # 定義分析維度 (Group By)
    dimensions: List[Literal[
        "Brand",        # 依品牌
        "Industry",     # 依產業
        "Agency",       # 依代理商
        "Ad_Format",    # 依格式
        "Date_Month",   # 依月份 (趨勢)
        "Date_Year"     # 依年份
    ]] = Field(default_factory=list, description="分析的切分維度 (Group By)")

    # 定義計算邏輯
    calculation_type: Literal["Total", "Ranking", "Trend", "Comparison"] = Field(
        "Total", description="分析模式：總計、排名、趨勢或比較"
    )


class SearchIntent(BaseModel):
    """
    使用者查詢意圖的結構化表示
    """
    intent_type: Literal["data_query", "greeting", "other"] = Field(
        ...,
        description="判斷使用者的意圖：'data_query' (查數據), 'greeting' (打招呼/閒聊), 'other' (無關問題)"
    )

    # 1. 過濾條件 (對應 SQL WHERE)
    brands: List[str] = Field(default_factory=list, description="品牌名稱列表，如 ['悠遊卡', 'Nike']")
    advertisers: List[str] = Field(default_factory=list, description="廣告主名稱列表")
    agencies: List[str] = Field(default_factory=list, description="代理商名稱列表")
    campaign_names: List[str] = Field(default_factory=list, description="廣告案件名稱列表")
    industries: List[str] = Field(default_factory=list, description="產業類別，如 ['金融', 'FMCG']")
    ad_formats: List[str] = Field(default_factory=list, description="廣告格式，如 ['Video', 'Banner']。對應使用者的「格式」")
    target_segments: List[str] = Field(default_factory=list, description="受眾/數據鎖定條件。對應使用者的「數據鎖定」")

    # 2. 時間條件 (獨立物件)
    date_range: DateRange = Field(default_factory=DateRange, description="查詢的時間範圍")

    # 3. 分析需求 (The Analysis Triad)
    analysis_needs: AnalysisNeeds = Field(
        default_factory=AnalysisNeeds, description="詳細的分析需求，包括指標、維度和計算類型"
    )

    # 4. 狀態控制
    missing_info: List[str] = Field(default_factory=list, description="缺少且必須追問的欄位，例如 ['date_range']")
    ambiguous_terms: List[str] = Field(default_factory=list, description="模糊不清、需要由 User 確認的詞彙")
    limit: Optional[int] = Field(None, description="資料筆數限制 (e.g. 50)")
