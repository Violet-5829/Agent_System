"""
图表写入工具 —— 由 analytics_save_chart Skill 调用。
在安全沙箱内执行 matplotlib 代码，输出 PNG 到 artifacts 目录。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main():
    """CLI 入口：stdin 接收 JSON，执行 matplotlib 代码，输出图表路径。"""
    raw = sys.stdin.read()
    args = json.loads(raw)

    chart_type = args.get("chart_type", "bar")
    title = args.get("title", "Chart")
    code = args.get("code", "")
    artifact_dir = args.get("artifact_dir", os.getcwd())

    if not code:
        print(json.dumps({"ok": False, "error": "code 参数为空"}))
        sys.exit(1)

    os.makedirs(artifact_dir, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # 构建安全的沙箱环境
    safe_globals = {
        "plt": plt,
        "pd": __import__("pandas"),
        "np": __import__("numpy") if __import__("importlib.util").util.find_spec("numpy") else None,
        "os": os,
        "artifact_dir": artifact_dir,
    }

    try:
        exec(code, safe_globals)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"图表生成失败: {e}"}))
        sys.exit(1)

    # 保存图表
    chart_path = os.path.join(artifact_dir, f"{title.replace(' ', '_')}.png")
    try:
        fig = plt.gcf()
        fig.savefig(chart_path, dpi=100, bbox_inches="tight")
        plt.close("all")
        print(json.dumps({
            "ok": True,
            "chart_path": chart_path,
            "chart_type": chart_type,
            "title": title,
        }))
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"图表保存失败: {e}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
