# ui.py
import chainlit as cl
import requests
import os
import json
from typing import AsyncIterator

# LangServe backend URL
LANGSERVE_URL = os.getenv("LANGSERVE_URL", "http://backend:8000/agent")

@cl.on_chat_start
async def start():
    """初始化對話"""
    await cl.Message(
        content="""# 歡迎使用 Text-to-SQL AI Agent 🚀

**功能介紹**:
- 🔍 自然語言查詢 MySQL 和 ClickHouse 資料庫
- 📊 自動生成 SQL 並返回分析結果
- 🤖 智能意圖分析和實體識別

**查詢範例**:
1. "悠遊卡股份有限公司，時間2025年，投遞的格式、成效、數據鎖定格式投資金額"
2. "幫我查 2024 Q4 所有活動的 CTR 和 VTR"
3. "展碁國際預算 Top 5 的活動是哪些？"

請輸入您的查詢 ⬇️
""",
    ).send()

    # 初始化 session
    cl.user_session.set("thread_id", None)

@cl.on_message
async def main(message: cl.Message):
    """處理用戶訊息"""

    # 顯示思考狀態
    thinking_msg = cl.Message(content="🤔 思考中...", author="System")
    await thinking_msg.send()

    # 準備輸入 (LangServe 格式)
    input_data = {
        "input": {
            "messages": [
                {"content": message.content, "type": "human"}
            ]
        },
        "config": {
            "configurable": {
                "thread_id": cl.user_session.get("thread_id") or "default"
            }
        }
    }

    try:
        # 使用 streaming 端點
        response = requests.post(
            f"{LANGSERVE_URL}/stream",
            json=input_data,
            stream=True,
            timeout=300  # 5 分鐘超時
        )
        response.raise_for_status()

        # 移除思考訊息
        await thinking_msg.remove()

        # 處理 streaming 輸出
        final_content = ""
        current_msg = None

        for line in response.iter_lines():
            if not line:
                continue

            # LangServe streaming 格式: data: {...}
            line_text = line.decode('utf-8')
            if not line_text.startswith('data: '):
                continue

            try:
                data = json.loads(line_text[6:])  # 移除 'data: ' prefix
                # print(f"DEBUG: Received chunk: {data}") # Debug log

                # 處理不同類型的 chunk - LangGraph Stream 結構
                # 1. 檢查是否有直接的 messages 更新 (通常在 updates 中)
                messages_list = []
                
                # Case A: Standard LangGraph 'values' or 'updates'
                if isinstance(data, dict):
                    # 嘗試從不同位置提取 messages
                    possible_sources = [
                        data.get('messages'), 
                        data.get('updates', {}).get('messages'),
                        data.get('values', {}).get('messages')
                    ]
                    
                    # 針對特定節點的輸出 (e.g., ResponseSynthesizer)
                    for node_name, node_output in data.items():
                        if isinstance(node_output, dict) and 'messages' in node_output:
                            possible_sources.append(node_output['messages'])

                    for source in possible_sources:
                        if source and isinstance(source, list):
                            messages_list.extend(source)
                        elif source and isinstance(source, dict) and 'content' in source:
                             messages_list.append(source)

                # 處理提取到的訊息
                for msg in messages_list:
                    content = ""
                    msg_type = ""
                    
                    if isinstance(msg, dict):
                        content = msg.get('content', "")
                        msg_type = msg.get('type', "")
                    elif hasattr(msg, 'content'): # Handle objects if deserialized
                        content = msg.content
                        msg_type = getattr(msg, 'type', "")

                    # 只顯示 AI 的訊息，且內容不為空
                    if content and msg_type == 'ai':
                        # 如果是完整的最終回應（通常比較長），直接顯示
                        final_content = content
                        
                        if current_msg:
                            current_msg.content = final_content
                            await current_msg.update()
                        else:
                            current_msg = cl.Message(content=final_content, author="AI Agent")
                            await current_msg.send()

            except json.JSONDecodeError:
                # 略過無法解析的行
                continue

        # 如果沒有 streaming 輸出，顯示最終內容
        if not current_msg and final_content:
            await cl.Message(
                content=final_content,
                author="AI Agent"
            ).send()
        elif current_msg and final_content and current_msg.content != final_content:
            # 確保最終內容完整顯示
            current_msg.content = final_content
            await current_msg.update()

    except requests.exceptions.Timeout:
        await cl.Message(
            content="⏰ 查詢超時，請稍後再試或簡化查詢條件。",
            author="Error"
        ).send()

    except requests.exceptions.ConnectionError:
        await cl.Message(
            content=f"""❌ 無法連接到後端服務

**可能原因**:
- 後端服務未啟動
- Docker 網路配置問題
- URL 設定錯誤: {LANGSERVE_URL}

請檢查 `docker-compose logs backend` 查看後端狀態。
""",
            author="Error"
        ).send()

    except requests.exceptions.HTTPError as e:
        error_detail = ""
        try:
            error_detail = e.response.json()
        except:
            error_detail = e.response.text

        await cl.Message(
            content=f"""❌ HTTP 錯誤 {e.response.status_code}

**錯誤詳情**:
```
{error_detail}
```

請檢查後端日誌以獲取更多資訊。
""",
            author="Error"
        ).send()

    except Exception as e:
        await cl.Message(
            content=f"""❌ 未知錯誤

**錯誤訊息**: {str(e)}

請聯繫系統管理員或查看日誌。
""",
            author="Error"
        ).send()

@cl.on_chat_end
async def end():
    """對話結束"""
    await cl.Message(
        content="感謝使用 Text-to-SQL Agent！👋",
        author="System"
    ).send()
