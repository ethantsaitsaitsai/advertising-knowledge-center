from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class QueryLevel(str, Enum):
    CONTRACT = "contract"        # 對應 cue_lists (總覽/財務)
    STRATEGY = "strategy"        # 對應 one_campaigns (波段/AM)
    EXECUTION = "execution"      # 對應 pre_campaign (投放/素材/格式)
    AUDIENCE = "audience"        # 對應 target_segments (受眾/數據)


class DateRange(BaseModel):
    """明確的時間區間物件，避免 List 索引錯誤"""
    start: Optional[str] = Field(None, description="開始日期 YYYY-MM-DD")
    end: Optional[str] = Field(None, description="結束日期 YYYY-MM-DD")


class ScopedTerm(BaseModel):
    """
    帶有搜尋範圍的模糊詞彙。
    讓 Agent 知道這個詞應該在哪個範圍內搜尋。
    """
    term: str = Field(..., description="模糊詞彙本身，例如 '亞思博'")
    # Relaxed to str to avoid validation errors
    scope: str = Field(
        "all", description="搜尋範圍。建議值: all, brands, advertisers, agencies, campaign_names, industries, keywords"
    )


class AnalysisNeeds(BaseModel):
    """詳細定義分析需求"""

    # Relaxed strict Enum to List[str] to prevent validation loops
    # We will handle validation/mapping in the node logic or downstream
    metrics: List[str] = Field(
        default_factory=list, 
        description="要計算的數值指標 (e.g., 'Budget_Sum', 'CTR_Calc', 'Impression_Sum')"
    )

    dimensions: List[str] = Field(
        default_factory=list, 
        description="分析的切分維度 (e.g., 'Ad_Format', 'Campaign_Name', 'Date_Month')"
    )

    # 定義計算邏輯
    calculation_type: Literal["Total", "Ranking", "Trend", "Comparison"] = Field(
        "Total", description="分析模式：總計、排名、趨勢或比較"
    )
    display_segment_category: bool = Field(default=False, description="如果使用者想查看受眾分類作為一個維度，設為 True。")


class SearchIntent(BaseModel):
    """
    使用者查詢意圖的結構化表示
    """
    intent_type: Literal["data_query", "greeting", "other"] = Field(
        ...,
        description="判斷使用者的意圖：'data_query' (查數據), 'greeting' (打招呼/閒聊), 'other' (無關問題)"
    )

    query_level: QueryLevel = Field(
        QueryLevel.STRATEGY, 
        description="The hierarchical level of the query. Determines the FROM table."
    )
    primary_entity: Optional[str] = Field(
        None,
        description="The primary entity name (e.g. '悠遊卡', 'Nike') found in the query."
    )
    needs_performance: bool = Field(
        False, 
        description="Whether to query ClickHouse for performance metrics (Impression, Click...)."
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
    
    # ambiguous_terms uses ScopedTerm
    ambiguous_terms: List[ScopedTerm] = Field(default_factory=list, description="模糊不清、需要由 User 確認的詞彙及其搜尋範圍")
    
    limit: int = Field(20, description="資料筆數限制 (預設 20)")
