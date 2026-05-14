# 图表保存

使用 matplotlib 生成数据可视化图表，保存为 PNG 文件。

## 工具名称
analytics_save_chart

## 参数
- `chart_type` (string): 图表类型 — bar / line / scatter / pie / histogram
- `title` (string): 图表标题
- `code` (string): 生成图表的 Python 代码（使用 matplotlib）

## 说明
- 图表自动保存到当前运行的 artifacts 目录
- 可使用 pd (pandas) 和 np (numpy) 读取物化数据
- 图表文件名由 title 自动生成

## 示例
```
chart_type: bar
title: 各部门人数统计
code: |
  import pandas as pd
  df = pd.read_parquet(f"{artifact_dir}/input.parquet")
  dept = df.groupby("department").size()
  plt.bar(dept.index, dept.values)
  plt.xlabel("部门")
  plt.ylabel("人数")
```
