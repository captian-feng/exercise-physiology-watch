# 运动生理文献库

按期刊、专题和日期浏览人体运动、训练表现与运动生理文献。网页保留中文译名、英文题名、DOI 和原文入口。

## 课题组如何维护

| 需要改什么 | 修改位置 |
| --- | --- |
| 新增期刊或修正 ISSN | journals.txt |
| 增加跨刊 PubMed 专题，或更新期刊 RSS | sources.json |
| 调整纳入和排除规则 | screening.py |
| 调整专题归类 | presentation.py |
| 维护英中文全称、缩写和译法 | exercise_glossary.json |
| 调整页面样式和筛选交互 | site-src/ |

欢迎用 Issue 提出需求，或从自己的分支提交 Pull Request。增补期刊时请附期刊官方链接、ISSN 和纳入理由。调整筛选规则时请附几条应保留或应排除的示例题名。增补术语时请附该术语在英文文献中的常见写法和机器翻译的错误译法。PR 会自动校验配置、术语表、检查网页脚本并离线重建基线。期刊、采集和站点配置合并到 main 后会触发更新，有权限的维护者也可以手动运行。请通过源码修改页面，并将 archive-state 留给自动更新流程。

## 术语表和翻译

术语表 `exercise_glossary.json` 决定中文译名的准确性，它只在英文题名里出现对应术语时才生效，因此不会误改其他译文。每条术语有三个作用：

| 字段 | 作用 |
| --- | --- |
| `zh` | 规范中文译名 |
| `variants` | 机器翻译常见的错误中文写法，被替换成 `zh` |
| `aliases` / `abbreviations` | 英文同义写法和常用缩写，用于识别术语 |

翻译有三道保护：解码时限制重复片段（避免出现「活体活体活体」这类复读）、译文退化时自动重试一次、重试仍失败的题名不写入缓存并保留英文原题。历史缓存里已经退化的译文会在下次运行时丢弃并重译。

本地校验术语表：

    python scripts/check_glossary.py

## 首次部署

1. 把项目推送到课题组指定的 GitHub 仓库默认分支。
2. 在 Settings → Pages 把 Source 设为 GitHub Actions。
3. 在 Actions 中打开「更新运动生理文献库」，从默认分支手动运行一次。检查来源状态、纳入数和部署结果，然后用匿名浏览器访问 Pages 网址。
4. GitHub Pages 首次更新验证成功后，再将它作为课题组的固定入口。已有站点可保留到新入口验证完成。

## 日常更新和故障恢复

- GitHub Actions 每天北京时间 07:30 和 11:00 运行。实际发布时间仍取决于 GitHub 和外部数据源，定时任务可能延迟或漏跑。
- 初次从仓库中的压缩 SQLite 起始快照恢复。此后读取 archive-state 分支，保留历史题录、已翻译标题和各来源的采集进度。任务串行运行，状态更新使用正常 Git 推送。只有 dist 作为 Pages 站点发布。
- 每次运行的 Summary 列出失败来源和待译标题。单个来源失败时，保留其上次成功位置，后续继续补查。整次采集失败时，Pages 保留上次成功版本。恢复后可用 Run workflow 手动补跑。
- 已配置的官网「最新文章／在线首发／当前卷期」按页面采集。文章的在线发表日期不影响这条采集路径，当前卷期有分页时会逐页读取。仍缺官网卷期入口的刊物用 Crossref 的正式出版日期补查，Crossref 和 PubMed 增量继续独立运行。官网入口在 sources.json 的 publisher_pages 中维护。
- Crossref 和 PubMed 分别限速，暂时性错误会重试。PubMed 查询太大时，按入库日期拆分。期刊官网首发与正式目录仍需逐刊对账，来源状态不能替代覆盖率核验。
- 可以设置默认分支合并需通过「检查协作改动」并经维护者审核。自动归档所用的 archive-state 分支需要允许 Actions 正常推送。

## DeepSeek 历史回填

百篇试译队列已关闭；其他历史题录的 AI 中文标题与摘要简介通过**手动回填**完成，范围仅限网站上实际展示的题录，未纳入的文献不会被翻译。

在 Actions 中手动运行「更新运动生理文献库」时勾选 `deepseek_backfill`，可设置本次调用上限 `backfill_batch`（默认 300）和累计预算 `backfill_budget`（默认 1200）。回填只在 DeepSeek 官方非高峰时段发出请求，忙时的运行会安全跳过；已翻译或已尝试过的题录不会重复调用，失败项也会被记录以免反复重试。用完预算后必须手动提高上限才会继续。实际请求数、输入/输出 token 与估算费用见每次运行日志；账单以 DeepSeek 账户为准。

如需**无限制全量补齐简介**，手动运行时勾选 `deepseek_backfill`，并把 `backfill_batch` 和 `backfill_budget` 都填 **-1**（负数=取消所有上限；`deepseek_full` 开关待工作流权限开放后也可直接使用）。该模式遍历所有网站已收录、尚缺简介的题录，不设调用次数、累计预算和非高峰时段限制；摘要按 PubMed → Europe PMC → Crossref → OpenAlex → Europe PMC(DOI) → Frontiers → 期刊页面 meta 的顺序逐条查找，任一来源拿到摘要即用，单个来源失败不影响下一条；Semantic Scholar 仅在配置了 `S2_API_KEY` 时启用（匿名访问会被限流）。已有简介的题录会跳过，避免重复调用。并发数由 `DEEPSEEK_FULL_WORKERS` 控制（默认 20）。

全量模式为避免被 GitHub 单次作业 50 分钟硬上限中断而丢失进度，内部设置 1800 秒（30 分钟）运行窗口，并在到点时取消尚未开始的请求、把已完成结果写回归档；外层子进程超时为 21000 秒，仅作为兜底。重新运行同一开关即可续跑，不会重头开始。实际请求数、输入/输出 token 与估算费用见每次运行日志；账单以 DeepSeek 账户为准。

DeepSeek 官方定价与忙闲时段以其文档为准：https://api-docs.deepseek.com/quick_start/pricing/
- GitHub 会暂停长时间无活动的公开仓库定时工作流。更新停滞时可先检查 Actions 中该流程是否已停用。https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows

## 本地验证

运行以下命令可检查配置与初始快照。

    python scripts/check_journals.py
    node --check site-src/app.js
    python -X utf8 cloud_refresh.py --render-only 2026-11-20

完整采集需要 Python 3.12 或兼容版本、网络以及 requirements.txt 中的本地翻译依赖。模型首次使用时从 Argos 下载并验证文件哈希。

词汇库按英文题名确认术语后，才对译文中的已知错误译法进行替换。缩写作为参考信息保存，具有多义性的缩写不会单独触发替换。保留原始英文标题供核对。

## 术语库如何扩充

术语库目前覆盖运动生理、训练学、生物力学、运动医学、分子免疫、环境生理、可穿戴、营养代谢、研究方法、解剖肌肉、人群与影像技术等类别。扩充来源有两条，都基于真实语料而不是凭空想词：

1. **标题词频**：统计归档英文题名里的二元、三元短语，挑出真实术语后人工定稿译名。片段（例如 `mass index`）不收，因为它会污染完整术语。
2. **摘要词频**：标题里很少出现的测量学、统计学词汇主要藏在摘要中，先抓取再用。

抓取摘要（维护脚本，不进 CI）：

    python scripts/fetch_abstracts.py --output abstracts.json --limit 2000

输出的 `abstracts.json` 是工作文件，不要提交。挑出候选术语后：

- 译名必须是地道的中文专业表达，不能是逐词拼接（`rotator cuff` 是「肩袖」而不是「旋转袖」）
- `variants` 只放机器翻译**真实产生过**的错误写法，来自线上译文核对
- 增补后运行 `python scripts/check_glossary.py`：它会校验字段、大小写、重复项，并断言「把规范译名喂给修正函数必须原样返回」，防止错译变体污染正确译文

覆盖率可以这样自查：统计标题命中术语的比例，以及仍有英文残留的题名数量。

错译变体不靠猜，用 `scripts/mine_variants.py` 从线上站点反查：若某条标题含某术语、但译文里缺少该术语的规范译名，就把这些标题的中文片段与全库对比，挑出**过度出现**的片段——那就是模型对这个术语的习惯性错译，人工确认后填入 `variants`。

    python scripts/mine_variants.py --site dist/index.html --top 40
