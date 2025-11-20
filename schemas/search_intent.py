from pydantic import BaseModel, Field
from typing import Optional, List, Literal


class DateRange(BaseModel):
    """明確的時間區間物件，避免 List 索引錯誤"""
    start: Optional[str] = Field(None, description="開始日期 YYYY-MM-DD")
    end: Optional[str] = Field(None, description="結束日期 YYYY-MM-DD")


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
    industries: List[str] = Field(default_factory=list, description="產業類別，如 ['金融', 'FMCG']")
    ad_formats: List[str] = Field(default_factory=list, description="廣告格式，如 ['Video', 'Banner']。對應使用者的「格式」")
    target_segments: List[str] = Field(default_factory=list, description="受眾/數據鎖定條件。對應使用者的「數據鎖定」")

    # 2. 時間條件 (獨立物件)
    date_range: DateRange = Field(default_factory=DateRange, description="查詢的時間範圍")

    # 3. 分析指標 (對應 SQL SELECT / Calculation)
    metrics: List[str] = Field(
        default_factory=list,
        description="需要的指標，標準化值為: ['Budget', 'Performance', 'Impression', 'CTR']"
    )

    # 4. 狀態控制
    missing_info: List[str] = Field(default_factory=list, description="缺少且必須追問的欄位，例如 ['date_range']")
    ambiguous_terms: List[str] = Field(default_factory=list, description="模糊不清、需要由 User 確認的詞彙")
