# ui.py
import os
import json
import httpx
import chainlit as cl
from langchain_core.messages import HumanMessage
from agent.graph import app
from agent.state import AgentState
import uuid

# LangServe backend URL
LANGSERVE_URL = os.getenv("LANGSERVE_URL", "http://backend:8000/agent")

@cl.password_auth_callback
def auth(username: str, password: str):
    """
    簡單的密碼驗證回調函數。
    使用者名稱可以是任意值，但密碼必須匹配環境變數設定。
    """
    auth_password = os.getenv("CHAINLIT_AUTH_PASSWORD")
    
    # 如果未設定環境變數，則不進行驗證（或是您可以選擇預設禁止）
    if not auth_password:
        return cl.User(identifier=username)

    if password == auth_password:
        return cl.User(identifier=username)
    
    return None

@cl.on_chat_start
async def start():
    """初始化對話"""
    await cl.Message(
        content="""# 歡迎使用廣告知識中心 🚀

**功能介紹**:
- 🔍 自然語言查詢 MySQL 和 ClickHouse 資料庫
- 📊 自動生成 SQL 並返回分析結果
- 🤖 智能意圖分析和實體識別

**查詢範例**:
1. "悠遊卡股份有限公司，時間2025年，投遞的格式、成效、數據鎖定格式投資金額"
2. "代理商 YTD(Year to Date) 認列金額 (截至最新月份)"
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
        # 使用 httpx AsyncClient 避免阻塞 Event Loop
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", f"{LANGSERVE_URL}/stream", json=input_data) as response:
                
                if response.status_code != 200:
                    # 處理非 200 錯誤
                    error_detail = await response.aread()
                    await cl.Message(
                        content=f"❌ HTTP 錯誤 {response.status_code}\n\n{error_detail.decode()}",
                        author="Error"
                    ).send()
                    return

                current_msg = None
                
                # 節點狀態對照表 (根據完成的節點提示下一步)
                NODE_STATUS_MAP = {
                    "InputAdapter": "🧠 正在分析您的查詢意圖...",
                    "IntentRouter": "🔍 正在查詢資料庫與分析數據...",  # 這步通常最久
                    "DataAnalyst": "✍️ 正在整理分析結果...",
                }

                # Async iterate over lines
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    if not line.startswith('data: '):
                        continue

                    try:
                        data = json.loads(line[6:])  # 移除 'data: ' prefix
                        
                        # Debug Logging
                        with open("ui_debug.log", "a") as f:
                            f.write(f"Chunk received: {json.dumps(data, ensure_ascii=False)}\n")

                        # --- 狀態更新邏輯 ---
                        # 檢查哪個節點正在輸出，並更新思考訊息
                        if isinstance(data, dict):
                            for node_name in data.keys():
                                if node_name in NODE_STATUS_MAP:
                                    status_text = NODE_STATUS_MAP[node_name]
                                    # 如果狀態改變了，更新訊息
                                    if thinking_msg.content != status_text:
                                        thinking_msg.content = status_text
                                        await thinking_msg.update()

                        messages_list = []
                        
                        # Helper: Recursive search
                        def find_messages_recursively(obj):
                            found = []
                            if isinstance(obj, dict):
                                for k, v in obj.items():
                                    if k == 'messages' and isinstance(v, list):
                                        found.extend(v)
                                    elif isinstance(v, (dict, list)):
                                        found.extend(find_messages_recursively(v))
                            elif isinstance(obj, list):
                                for item in obj:
                                    found.extend(find_messages_recursively(item))
                            return found

                        if isinstance(data, dict):
                            if 'ResponseSynthesizer' in data:
                                node_data = data['ResponseSynthesizer']
                                if 'messages' in node_data:
                                    messages_list.extend(node_data['messages'])
                            elif 'updates' in data:
                                messages_list.extend(find_messages_recursively(data['updates']))
                            if not messages_list:
                                search_data = {k: v for k, v in data.items() if k != 'values'}
                                messages_list.extend(find_messages_recursively(search_data))

                        for msg in messages_list:
                            content = ""
                            msg_type = ""
                            
                            if isinstance(msg, dict):
                                content = msg.get('content', "")
                                msg_type = msg.get('type', "")
                            elif hasattr(msg, 'content'): 
                                content = msg.content
                                msg_type = getattr(msg, 'type', "")
                            
                            if content and msg_type == 'ai':
                                final_content = content
                                # 一旦開始生成最終回應，移除思考訊息
                                await thinking_msg.remove()
                                
                                if current_msg:
                                    current_msg.content = final_content
                                    await current_msg.update()
                                else:
                                    current_msg = cl.Message(content=final_content, author="AI Agent")
                                    await current_msg.send()

                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        with open("ui_debug.log", "a") as f:
                            f.write(f"Error processing chunk: {e}\n")
                        continue
                
                # 確保迴圈結束後思考訊息被移除 (如果還沒移除的話)
                await thinking_msg.remove()

    except httpx.TimeoutException:
        await cl.Message(
            content="⏰ 查詢超時，請稍後再試或簡化查詢條件。",
            author="Error"
        ).send()

    except httpx.RequestError as e:
        await cl.Message(
            content=f"❌ 無法連接到後端服務: {str(e)}\n\n請檢查後端是否啟動。",
            author="Error"
        ).send()

    except Exception as e:
        await cl.Message(
            content=f"❌ 未知錯誤: {str(e)}",
            author="Error"
        ).send()
