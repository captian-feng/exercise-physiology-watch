# 运动生理文献库 · 每日协作核对指令

> 复制给任意 AI（Claude / ChatGPT / Gemini / 本地模型均可）执行。
> 所有 AI 执行同一份指令、写同一个仓库，靠「提交前重读合并」避免互相覆盖。

---

## 一、你要做什么

每个 AI 每天只做一件事：**核对「今天新收录」的文献类型，把有把握的写入仓库，没把握的保持不动。**

不要全库扫描，不要处理往期遗留。今天的活今天干完。

---

## 二、数据从哪来

**唯一权威数据源**（每次现取，不要用缓存）：

```
https://captian-feng.github.io/exercise-physiology-watch/
```

页面里有一个 JSON：

```html
<script id="dataset" type="application/json">{...}</script>
```

关键字段：

| 字段 | 含义 |
|---|---|
| `updated` | 站点数据日期，如 `2026-11-26` |
| `records` | 全部记录数组 |
| `articleTypes` | 7 种类型名，顺序固定 |
| `tiers` | `["core","related"]` |
| `venues` | 期刊名数组 |

每条 `records[i]`：

| 字段 | 含义 |
|---|---|
| `e` | 英文题名 |
| `z` | 中文题名 |
| `d` | DOI |
| `m` | PMID |
| `a` | 类型索引（对应 `articleTypes[a]`） |
| `r` | 分区：`0`=核心区，`1`=相关拓展 |
| `s` | **本站首次收录日期** ← 判断「今天新增」的依据 |
| `p` | 发表日期 |
| `j` | 期刊索引（对应 `venues[j]`） |

### ⚠️ 页面数据只有题名，没有摘要

这是最关键的限制。你只有英文题名 + 中文题名 + 期刊名。

**结论：能判断的只有「类型」（研究/综述/社论/会议摘要），判断不了「是否该收录」。** 后者需要摘要，不在本任务范围内。

---

## 三、筛选「今天的活」

```python
P = dataset["articleTypes"].index("类型待确认")
today = dataset["updated"]
todo = [r for r in dataset["records"]
        if r["s"] == today and r["a"] == P]
```

**只处理 `todo`。** 已确认类型的一律跳过 —— 那就是「相同内容略过」。

参考量级（2026-11-26）：当天新增 4,747 条，待确认 2,401 条（核心区 1,472 + 相关区 929）。

---

## 四、怎么判断类型

### 7 种类型

| 类型 | 靠题名识别 |
|---|---|
| `原创研究` | 有明确研究设计词（randomized / controlled trial / cohort / cross-sectional / pilot study），或题名描述了一个具体测量与结果 |
| `系统综述与证据整合` | systematic review / meta-analysis / scoping review / umbrella review / narrative review |
| `方案与注册` | 以 protocol / study protocol / rationale and design 开头或结尾 |
| `指南、共识与立场文件` | position stand / consensus statement / guideline / recommendation for practice |
| `会议摘要、海报与会议论文` | 题名含会议摘要编号（如 `D2.S1.1`、`P14`），或增刊期号 |
| `评论、社论与勘误` | 以 Editorial / Commentary / Letter to / Reply to / Response to / Correction / Erratum 开头 |
| `类型待确认` | **以上都不确定时，保持原样** |

### 金规则

**拿不准就留 `类型待确认`，不要猜。**

用户明确要求过：宁可留着待确认，也不要把错的录进去。错分类比没分类更糟。

### 题名的常见陷阱

| 题名样子 | 正确判断 |
|---|---|
| `Response to: Methodological rigor in...` | 评论、社论与勘误（不是原创研究） |
| `... : a systematic review and meta-analysis` | 系统综述（不是原创研究） |
| `Correction to: Sprint training and performance` | 评论、社论与勘误 |
| `Study protocol for a randomized controlled trial` | 方案与注册（不是原创研究） |
| `... : an infographic` | 评论、社论与勘误 |
| `ACSM position stand on...` | 指南、共识与立场文件 |
| `Effects of X on Y in Z` | 通常是原创研究 |
| `Exercise and hypertension: mechanisms and implications` | **不确定** → 留待确认 |

最后两条要特别注意：**药理学/机制类综述（protective effect、therapeutic potential、underlying mechanisms）常常是综述而非原创研究，但只要题名没有明确写 review，就该留待确认。**

---

## 五、写入格式（最容易出错的地方）

文件：仓库根目录 `article_type_overrides.json`

```json
{
  "10.1234/example.2026.123": "原创研究",
  "pmid:42241674": "系统综述与证据整合"
}
```

### 硬性规则

1. **键必须是裸 DOI**（小写、无前缀）。写成 `doi:10.1234/...` 会被系统**静默忽略** —— 这是我踩过的坑，24 条修改因此全部失效且无报错。
2. **没有 DOI 但有 PMID** 的，用 `pmid:12345678`。
3. 两个都没有的，**跳过**（当天数据里这类为 0 条）。
4. 值必须是 7 种类型之一，**不能写 `类型待确认`**（那等于没改）。
5. 只写有把握的。**一次写入 30–100 条高质量的，好过硬塞 500 条。**

---

## 六、提交前必须做：重读 + 合并

**多个 AI 写同一个文件，这是唯一的防冲突手段。** 顺序不能变：

```
1. 从 GitHub 重新读取最新的 article_type_overrides.json
2. 在你自己的改动基础上，保留别人已经写入的条目
3. 用「最新的作为底 + 你的新增」合并
4. 提交
```

如果第 1 步和第 3 步之间文件被改了，**重新来一次**（重读 → 合并 → 提交）。

合并规则：
- 别人已写入的键：**保留，不覆盖**（即使你认为他们错了 —— 留给人工裁决）
- 只有你新增的键才写入

---

## 七、提交方式

**方式 A：Pull Request（推荐，适合所有 AI）**

```
分支名：classify/<你的名字>-<日期>
例如：classify/claude-20261126
```

标题：`Classify N papers first seen on YYYY-MM-DD`

PR 自动跑 CI 校验，通过后由维护者合并。

**方式 B：直接提交 main**

只有拿到写入权限的 AI 才可以，仍需遵守第六节的合并规则。

> 不要碰 `archive-state` 分支 —— 那是自动采集的存档，手动改会被下次采集覆盖。

---

## 八、做完后报告什么

在 PR 描述或最终回复里写清：

```
今日新增待确认：2,401 条
本次处理：       120 条
  原创研究：      87
  系统综述：      21
  评论社论：      12
保持待确认：   2,281 条（无摘要/无法判定）
```

这样**你和别的 AI 都能看到同一份统计**，明确谁做了哪部分，避免重复劳动。

---

## 九、怎么避免和其他 AI 撞车

在 PR 描述里注明你处理的是**哪一批**。建议按顺序切片分工：

| AI | 处理范围 |
|---|---|
| AI-1 | `todo[0:800]` |
| AI-2 | `todo[800:1600]` |
| AI-3 | `todo[1600:2401]` |

或者按分区：一个 AI 做核心区，另一个做相关区。

**开工前先看一眼最近的 PR 和 commit**，确认哪些已经被做掉。

---

## 十、一次完整执行的伪代码

```python
import json, re, urllib.request, base64

# 1. 取数据
html = urllib.request.urlopen(
    "https://captian-feng.github.io/exercise-physiology-watch/").read().decode()
ds = json.loads(re.search(
    r'<script id="dataset" type="application/json">(.*?)</script>', html, re.S).group(1))

# 2. 今天的活
P = ds["articleTypes"].index("类型待确认")
todo = [r for r in ds["records"] if r["s"] == ds["updated"] and r["a"] == P]

# 3. 逐条判断（靠你的阅读能力，不是关键词）
assignments = {}
for r in todo:
    key = (r.get("d") or "").lower() or (f"pmid:{r['m']}" if r.get("m") else None)
    if not key:
        continue
    verdict = judge(r["e"])            # 你的判断
    if verdict and verdict != "类型待确认":
        assignments[key] = verdict

# 4. 重读远端 → 合并 → 提交   ← 不要跳过
#    remote = 重新拉取的 article_type_overrides.json
#    remote.update(assignments)   # 别人的保留，自己的是新增
```

---

## 十一、常见错误清单（照抄踩过的坑）

| 错误 | 后果 |
|---|---|
| 键写成 `doi:10.1234/...` | **静默失效**，不报错 |
| 不重读就提交 | 覆盖其他 AI 的成果 |
| 拿不准硬猜 | 错误类型上线，比待确认更糟 |
| 把 `Response to:` 判成原创研究 | 评论类文献混入研究列表 |
| 把 `: a systematic review` 判成原创研究 | 综述混入原创研究 |
| 改 `archive-state` 分支 | 下次自动采集覆盖你的修改 |
| 写 `类型待确认` 作为值 | 等于没改 |

---

## 十二、一句话版本（直接贴进定时任务）

> 打开 `https://captian-feng.github.io/exercise-physiology-watch/`，从页面中取出 `<script id="dataset">` 的 JSON。找出 `s` 字段等于 `updated`（今天）且类型为「类型待确认」的记录，逐条阅读英文题名判定文献类型。有把握的以**裸 DOI**（小写、无 `doi:` 前缀）为键，无 DOI 则用 `pmid:xxx`，写入仓库根目录 `article_type_overrides.json`；拿不准的保持不动。提交前必须重新从 GitHub 读取该文件，保留他人已写入的条目，只追加不覆盖。完成后报告：处理了多少条、各类型各多少、还有多少保持待确认。
