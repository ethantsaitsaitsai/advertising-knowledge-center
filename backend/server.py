# server.py
from fastapi import FastAPI
from langserve import add_routes
from agent.graph import app as langgraph_app
import uvicorn
import os

fastapi_app = FastAPI(
    title="Text-to-SQL Agent API",
    version="1.0",
    description="API for accessing the LangGraph SQL Agent"
)

# 將 LangGraph 註冊為 API 路由
# 自動生成 /agent/invoke, /agent/stream, /agent/playground 等端點
add_routes(
    fastapi_app,
    langgraph_app,
    path="/agent",
    enable_feedback_endpoint=True,  # 啟用反饋端點
    # debug_mode=True  # 開啟 debug 模式可以顯示更多中間步驟
)

if __name__ == "__main__":
    # 這裡的 host 和 port 可以透過環境變數控制，以適應 Docker 環境
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", 8000))
    uvicorn.run(fastapi_app, host=host, port=port)
