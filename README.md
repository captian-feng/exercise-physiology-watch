# 运动生理文献库

按期刊、专题和日期浏览人体运动、训练表现与运动生理文献。网页保留中文译名、英文题名、DOI 和原文入口。

## 课题组如何维护

| 需要改什么 | 修改位置 |
| --- | --- |
| 新增期刊或修正 ISSN | journals.txt |
| 增加跨刊 PubMed 专题，或更新期刊 RSS | sources.json |
| 调整纳入和排除规则 | screening.py |
| 调整专题归类和翻译术语 | presentation.py |
| 调整页面样式和筛选交互 | site-src/ |

欢迎用 Issue 提出需求，或从自己的分支提交 Pull Request。增补期刊时请附期刊官方链接、ISSN 和纳入理由。调整筛选规则时请附几条应保留或应排除的示例题名。PR 会自动校验配置、检查网页脚本并离线重建基线。期刊、采集和站点配置合并到 main 后会触发更新，有权限的维护者也可以手动运行。请通过源码修改页面，并将 archive-state 留给自动更新流程。

## 首次部署

1. 把项目推送到课题组指定的 GitHub 仓库默认分支。
2. 在 Settings → Pages 把 Source 设为 GitHub Actions。
3. 在 Actions 中打开「更新运动生理文献库」，从默认分支手动运行一次。检查来源状态、纳入数和部署结果，然后用匿名浏览器访问 Pages 网址。
4. GitHub Pages 首次更新验证成功后，再将它作为课题组的固定入口。已有站点可保留到新入口验证完成。

## 日常更新和故障恢复

- GitHub Actions 每天北京时间 08:17 运行。选择非整点可减少高负载时的排队，实际发布时间仍取决于 GitHub 和外部数据源。
- 初次从仓库中的压缩 SQLite 起始快照恢复。此后读取 archive-state 分支，保留历史题录、已翻译标题和各来源的采集进度。任务串行运行，状态更新使用正常 Git 推送。只有 dist 作为 Pages 站点发布。
- 每次运行的 Summary 列出失败来源和待译标题。单个来源失败时，保留其上次成功位置，后续继续补查。整次采集失败时，Pages 保留上次成功版本。恢复后可用 Run workflow 手动补跑。
- Crossref 和 PubMed 分别限速，暂时性错误会重试。PubMed 查询太大时，按入库日期拆分。期刊官网首发与正式目录仍需逐刊对账，来源状态不能替代覆盖率核验。
- 可以设置默认分支合并需通过「检查协作改动」并经维护者审核。自动归档所用的 archive-state 分支需要允许 Actions 正常推送。
- GitHub 会暂停长时间无活动的公开仓库定时工作流。更新停滞时可先检查 Actions 中该流程是否已停用。https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows

## 本地验证

运行以下命令可检查配置与初始快照。

    python scripts/check_journals.py
    node --check site-src/app.js
    python -X utf8 cloud_refresh.py --render-only 2026-11-20

完整采集需要 Python 3.12 或兼容版本、网络以及 requirements.txt 中的本地翻译依赖。模型首次使用时从 Argos 下载并验证文件哈希。

