# server.py
import os
import sys

# Fix import path for agent module
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from fastapi import FastAPI, Request
from langserve import add_routes
from agent.graph import app as langgraph_app
import uvicorn
import os

fastapi_app = FastAPI(
    title="Text-to-SQL Agent API",
    version="1.0",
    description="API for accessing the LangGraph SQL Agent"
)

def _inject_thread_id(config: dict, request: Request) -> dict:
    """
    Middleware to ensure thread_id exists in the config.
    If the client provided it, it should already be in 'config'.
    If not, we inject a default one to prevent Checkpointer errors.
    """
    configurable = config.get("configurable", {})
    if "thread_id" not in configurable:
        print(f"⚠️  WARNING: thread_id missing in request config. Injecting default.")
        configurable["thread_id"] = "default_thread_id"
        config["configurable"] = configurable
    else:
        print(f"✅ Received thread_id: {configurable['thread_id']}")
    return config

# 將 LangGraph 註冊為 API 路由
# 自動生成 /agent/invoke, /agent/stream, /agent/playground 等端點
add_routes(
    fastapi_app,
    langgraph_app,
    path="/agent",
    enable_feedback_endpoint=True,
    per_req_config_modifier=_inject_thread_id # [NEW] Inject config modifier
)

if __name__ == "__main__":
    # 這裡的 host 和 port 可以透過環境變數控制，以適應 Docker 環境
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", 8000))
    uvicorn.run("backend.server:fastapi_app", host=host, port=port, reload=True)
