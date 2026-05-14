"""
监督者动态调度工作流提示词。
"""

SUPERVISOR_INTAKE_PROMPT = """你是一个分析任务监督者。分析以下用户需求并制定执行计划：

用户需求：{user_input}

现有专家：{workers}

请确定：
1. 核心分析目标是什么？
2. 需要拆分为哪些子任务？
3. 每个子任务适合分配给哪个专家？"""

DELEGATION_PROMPT = """当前分析周期：{cycle}/{max_cycles}
待处理焦点：{focus_task}

请选择最适合此任务的专家。只返回专家 ID。"""

REVIEW_PROMPT = """你是一个分析结果审查者。审查当前执行结果并决定下一步：

已完成任务：
{reports}

原始需求：{user_input}

请判断：
- continue: 还需继续分析
- stop: 分析已完成，可生成最终报告

只返回 "continue" 或 "stop"。"""

FINALIZE_SUPERVISOR_PROMPT = """请基于以下所有分析结果，生成最终综合分析报告：

用户需求：{user_input}

所有报告：
{reports}

请生成一份完整的分析报告（Markdown 格式，中文）。"""
