# SQL 只读查询

在已绑定的 SQL 数据源上执行只读 SELECT 查询。

## 工具名称
analytics_run_sql

## 参数
- `query` (string): 只读 SQL SELECT 语句

## 安全限制
- 仅允许 SELECT / WITH / EXPLAIN 语句
- 禁止多语句（分号分隔）
- 查询结果自动截断至配置的行数上限
- 超时自动中断

## 示例
```
query: SELECT department, COUNT(*) as cnt FROM employees GROUP BY department ORDER BY cnt DESC
```
