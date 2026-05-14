"""
SkillHub 客户端 —— 可选的外部技能市场集成。

首版为存根，留作 Phase D 或后续扩展。
"""

from __future__ import annotations


class SkillHubClient:
    """SkillHub 客户端（首版存根）。"""

    def __init__(self, api_key: str = "", base_url: str = "", timeout: int = 15):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def search(self, query: str, limit: int = 40) -> list[dict]:
        """搜索 Skill（存根）。"""
        return []

    def fetch_skill(self, skill_id: str) -> dict | None:
        """获取 Skill 详情（存根）。"""
        return None
