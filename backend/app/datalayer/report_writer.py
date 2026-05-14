"""
报表写入工具 —— 由 analytics_write_report_md Skill 调用。
将 Markdown 内容写入 artifacts 目录。
"""

from __future__ import annotations

import json
import os
import sys


def main():
    """CLI 入口：stdin 接收 JSON，写入 Markdown 报表。"""
    raw = sys.stdin.read()
    args = json.loads(raw)

    title = args.get("title", "Report")
    content = args.get("content", "")
    artifact_dir = args.get("artifact_dir", os.getcwd())

    if not content:
        print(json.dumps({"ok": False, "error": "content 参数为空"}))
        sys.exit(1)

    os.makedirs(artifact_dir, exist_ok=True)

    report_path = os.path.join(artifact_dir, f"{title.replace(' ', '_')}.md")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(json.dumps({
            "ok": True,
            "report_path": report_path,
            "title": title,
        }))
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"报表写入失败: {e}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
