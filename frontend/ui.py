# ui.py
import os
import json
import httpx
import asyncio
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

    # 狀態管理
    current_status = "🤔 思考中"
    stop_animation = False
    
    # 顯示思考狀態訊息
    thinking_msg = cl.Message(content=current_status, author="System")
    await thinking_msg.send()

    # 定義動畫任務：循環顯示 . .. ...
    async def animate_dots():
        while not stop_animation:
            for dots in ["", ".", "..", "..."]:
                if stop_animation: break
                try:
                    thinking_msg.content = f"{current_status}{dots}"
                    await thinking_msg.update()
                except Exception:
                    break
                await asyncio.sleep(0.5)
    
    # 啟動動畫背景任務
    animation_task = asyncio.create_task(animate_dots())

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
                    stop_animation = True # 停止動畫
                    # 處理非 200 錯誤
                    error_detail = await response.aread()
                    await cl.Message(
                        content=f"❌ HTTP 錯誤 {response.status_code}\n\n{error_detail.decode()}",
                        author="Error"
                    ).send()
                    return

                current_msg = None
                
                # 節點狀態對照表 (根據完成的節點提示下一步)
                # 注意：這裡不帶點點，因為動畫會自動補上
                NODE_STATUS_MAP = {
                    "InputAdapter": "🧠 正在分析您的查詢意圖",
                    "IntentRouter": "🔍 正在查詢資料庫與分析數據",  # 這步通常最久
                    "DataAnalyst": "✍️ 正在整理分析結果",
                }

                # Async iterate over lines
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    
                    if not line.startswith('data: '):
                        continue

                    try:
                        data = json.loads(line[6:])  # 移除 'data: ' prefix
                        
                        # --- 狀態更新邏輯 ---
                        if isinstance(data, dict):
                            for node_name in data.keys():
                                if node_name in NODE_STATUS_MAP:
                                    # 更新基礎文字，動畫任務會自動抓取並補上點點
                                    current_status = NODE_STATUS_MAP[node_name]

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
                                # 一旦開始生成最終回應，停止動畫並移除思考訊息
                                stop_animation = True
                                await thinking_msg.remove()
                                
                                final_content = content
                                if current_msg:
                                    current_msg.content = final_content
                                    await current_msg.update()
                                else:
                                    current_msg = cl.Message(content=final_content, author="AI Agent")
                                    await current_msg.send()

                    except json.JSONDecodeError:
                        pass
                    except Exception:
                        continue
                
                # 確保迴圈結束後動畫停止
                stop_animation = True

    except httpx.TimeoutException:
        stop_animation = True
        await cl.Message(
            content="⏰ 查詢超時，請稍後再試或簡化查詢條件。",
            author="Error"
        ).send()

    except httpx.RequestError as e:
        stop_animation = True
        await cl.Message(
            content=f"❌ 無法連接到後端服務: {str(e)}\n\n請檢查後端是否啟動。",
            author="Error"
        ).send()

    except Exception as e:
        stop_animation = True
        await cl.Message(
            content=f"❌ 未知錯誤: {str(e)}",
            author="Error"
        ).send()
    
    finally:
        # 最終確保動畫停止
        stop_animation = True
        try:
            await thinking_msg.remove()
        except:
            pass
