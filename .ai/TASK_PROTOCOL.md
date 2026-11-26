# 多智能体运动生理学文献库任务协议

所有外部 AI 必须先读取本文件和 SCHEMA.md，再读取最新主库与已有贡献。

每日只处理当天新增、当天首次可访问、智能体自有未入库记录，以及主库缺少关键字段的记录。按 PMID、DOI、规范化标题去重；已完整存在的记录标记为 skipped-existing。不得直接修改 main、catalog.sqlite.gz 或 dist/index.html，必须提交 contributions/<agent>/YYYY-MM-DD.md 和 .json 并创建 Pull Request。

英文标题和英文摘要必须保留原文。摘要应从期刊官网、出版社、PubMed、Europe PMC、Crossref 等来源尽可能获取；来源缺失使用 source-missing，不得编造。网页英文标题在上、中文标题在下，摘要按钮只显示中文摘要。

提交前必须检查 PMID/DOI 重复、Markdown/JSON 一致、英文原文未被改写、链接有效、字段完整、无凭据泄露。冲突保留双方信息并标记 needs-review。

