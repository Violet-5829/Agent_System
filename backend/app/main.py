"""
FastAPI 应用入口 —— 与参考仓库 main.py 结构对齐。
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes import router
from .store import store
from .runtime import llm_gateway


app = FastAPI(
    title="数据分析 Agent Playground API",
    description="面向数据分析的多智能体协同后端服务。",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "null"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    store.seed_defaults()
    # 从 store 恢复设置并刷新 LLM 客户端
    stored = store.get_app_settings_payload()
    if stored:
        llm_gateway.refresh_client()
    else:
        llm_gateway.refresh_client()


# 静态文件：artifacts（图表/报表可公开访问）
artifacts_dir = os.path.join(os.path.dirname(__file__), "..", "data", "artifacts")
os.makedirs(artifacts_dir, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=artifacts_dir), name="artifacts")

app.include_router(router)
