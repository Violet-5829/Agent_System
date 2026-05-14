# 报表生成

将分析结论写入 Markdown 报表文件，保存到 artifacts 目录。

## 工具名称
analytics_write_report_md

## 参数
- `title` (string): 报表标题
- `content` (string): Markdown 格式的报表内容

## 报表结构建议
1. 摘要（3-5句）
2. 数据概览（来源、规模、列说明）
3. 分析过程与关键发现
4. 图表引用
5. 建议与下一步

## 示例
```
title: 2025年度销售分析报告
content: |
  # 2025年度销售分析报告
  
  ## 摘要
  本报告基于2025年度销售数据...
```
