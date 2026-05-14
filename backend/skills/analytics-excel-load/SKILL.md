# Excel 数据加载

将已注册的 Excel 数据集文件物化为标准化 Parquet 格式。

## 工具名称
analytics_load_excel

## 参数
- `sheet_name` (string, 可选): 指定 Sheet 名称，不传则加载第一个 Sheet

## 安全限制
- 文件路径来自服务端已注册的 ExcelDataset，不允许模型传任意路径
- 路径必须在 EXCEL_DATA_ROOT 白名单下
- 物化结果写入 artifacts 目录

## 示例
```
sheet_name: Sheet1
```
