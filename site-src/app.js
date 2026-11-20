(() => {
  "use strict";

  const get = (id) => document.getElementById(id);
  // The payload stores venues, themes and tiers once and references them by
  // index, and rebuilds DOI links in the browser, which keeps the page about a
  // third smaller than storing the full strings on every record.
  const raw = JSON.parse(get("dataset").textContent);
  const data = {
    journals: raw.journals,
    topics: raw.topics,
    updated: raw.updated,
    records: raw.records.map((record) => ({
      journal: raw.venues[record.j],
      focused: record.f === 1,
      tier: raw.tiers[record.r],
      topic: raw.topics[record.t],
      clinical: record.c === 1,
      en: record.e,
      zh: record.z || "",
      doi: record.d,
      url: record.u || (record.d ? "https://doi.org/" + record.d : ""),
      published: record.p,
      seen: record.s,
    })),
  };
  const journal = get("journal");
  const topic = get("topic");
  const clinicalTag = "clinical-study";
  const clinicalLabel = "临床与疾病相关";
  const dateField = get("date-field");
  const dateSingle = get("date-single");
  const dateStart = get("date-start");
  const dateEnd = get("date-end");
  const query = get("query");
  const sort = get("sort");
  const form = get("filters");
  const articles = get("articles");
  const tabs = [...document.querySelectorAll("button[data-scope]")];
  const pageSize = 20;
  const collator = new Intl.Collator("zh-CN", { numeric: true, sensitivity: "base" });
  const journalRank = new Map(data.journals.map((name, index) => [name, index]));
  const topicRank = new Map(data.topics.map((name, index) => [name, index]));
  const allTopics = [...new Set(data.records.map(record => record.topic))];
  const allJournals = [...new Set([...data.journals, ...data.records.map(record => record.journal)])];
  let page = 1;
  let scope = "core";

  function normal(value) {
    return value.normalize("NFKC").toLowerCase();
  }

  function compareJournal(a, b) {
    return (journalRank.get(a) ?? journalRank.size) - (journalRank.get(b) ?? journalRank.size)
      || collator.compare(a, b);
  }

  function compareTopic(a, b) {
    return (topicRank.get(a) ?? topicRank.size) - (topicRank.get(b) ?? topicRank.size)
      || collator.compare(a, b);
  }

  function bounds(value) {
    if (!value) return null;
    const parts = value.split("-");
    const [year, month] = parts.map(Number);
    if (parts.length === 1) return [value + "-01-01", value + "-12-31"];
    if (parts.length === 2) {
      const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
      return [value + "-01", value + "-" + String(lastDay).padStart(2, "0")];
    }
    return [value, value];
  }

  const records = data.records.map(record => ({
    ...record,
    publishedBounds: bounds(record.published),
    searchable: normal([record.zh, record.en, record.doi].join(" ")),
  }));

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  }

  function addOptions(select, values) {
    for (const value of values) {
      const option = node("option", "", value);
      option.value = value;
      select.append(option);
    }
  }

  function addExclusion(value, label) {
    const option = node("label", "exclude-option");
    const control = node("input");
    control.type = "checkbox";
    control.name = "exclude-topic";
    control.value = value;
    option.append(control, node("span", "", label));
    get("excluded-topics").append(option);
  }

  function setScope(value) {
    scope = value;
    for (const tab of tabs) {
      tab.setAttribute("aria-pressed", String(tab.dataset.scope === scope));
    }
  }

  function time(value) {
    const element = node("time", "", value);
    element.dateTime = value;
    return element;
  }

  function articleRow(record, grouped) {
    const row = node("li", "article");
    const meta = node("div", "article-meta");
    const shownDate = record[dateField.value];
    meta.append(shownDate ? time(shownDate) : node("span", "", "发表日期未记录"));
    if (!grouped) {
      meta.append(node("span", "", record.journal), node("span", "topic", record.topic));
    }
    if (record.clinical) meta.append(node("span", "clinical-tag", clinicalLabel));
    if (!record.focused) meta.append(node("span", "", "刊外补漏"));
    const title = node("div", "article-title");
    if (record.url) {
      const link = node("a", "", record.zh || record.en);
      link.href = record.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      title.append(link);
    } else {
      title.textContent = record.zh || record.en;
    }
    row.append(meta, title);
    if (record.zh) {
      const original = node("p", "english", record.en);
      original.lang = "en";
      row.append(original);
    }
    return row;
  }

  function renderRows(rows) {
    if (sort.value === "recent") {
      const list = node("ul", "article-list");
      for (const record of rows) list.append(articleRow(record, false));
      articles.replaceChildren(list);
      return;
    }

    const grouped = document.createDocumentFragment();
    let previousJournal;
    let previousTopic;
    let section;
    let list;
    for (const record of rows) {
      if (record.journal !== previousJournal) {
        section = node("section", "journal-group");
        section.append(node("h3", "journal-heading", record.journal));
        grouped.append(section);
        previousJournal = record.journal;
        previousTopic = undefined;
      }
      if (record.topic !== previousTopic) {
        list = node("ul", "article-list");
        section.append(node("h4", "topic-heading", record.topic), list);
        previousTopic = record.topic;
      }
      list.append(articleRow(record, true));
    }
    articles.replaceChildren(grouped);
  }

  function matchesDate(record, start, end) {
    if (!start && !end) return true;
    const range = dateField.value === "published"
      ? record.publishedBounds
      : [record.seen, record.seen];
    return Boolean(range && range[0] && (!start || range[1] >= start) && (!end || range[0] <= end));
  }

  function dateLabel(value) {
    if (value.length === 4) return value + "（仅标注年份）";
    if (value.length === 7) return value + "（仅标注年月）";
    return value;
  }

  function setDateOptions(select, placeholder, options, current) {
    const first = node("option", "", placeholder);
    first.value = "";
    const entries = options.map(([value, label]) => {
      const option = node("option", "", label);
      option.value = value;
      return option;
    });
    select.replaceChildren(first, ...entries);
    select.disabled = !entries.length;
    select.value = options.some(([value]) => value === current) ? current : "";
  }

  function updateDates(candidates) {
    const counts = new Map();
    const field = dateField.value;
    for (const record of candidates) {
      const value = record[field];
      if (value) counts.set(value, (counts.get(value) || 0) + 1);
    }
    const values = [...counts.keys()].sort();
    const intervals = new Map(values.map(value => [value, bounds(value)]));
    const dates = new Set(values);
    const from = dates.has(dateStart.value) ? dateStart.value : "";
    const to = dates.has(dateEnd.value) ? dateEnd.value : "";
    const startDay = intervals.get(from)?.[0];
    const endDay = intervals.get(to)?.[1];
    const labels = values.map(value => [value, dateLabel(value)]);
    const single = labels.map(([value, label]) => [value, label + " · " + counts.get(value) + " 篇"]);

    setDateOptions(dateSingle, "全部日期", single.reverse(), dateSingle.value);
    setDateOptions(dateStart, "不限起始日期", labels.filter(([value]) =>
      !endDay || intervals.get(value)[0] <= endDay), from);
    setDateOptions(dateEnd, "不限结束日期", labels.filter(([value]) =>
      !startDay || intervals.get(value)[1] >= startDay), to);

    const help = get("date-help");
    if (!values.length) {
      help.textContent = candidates.length ? "当前结果未记录所选类型的日期。" : "当前条件下没有可用日期。";
    } else {
      const first = values[0];
      const last = values.reduce((latest, value) => intervals.get(value)[1] >= intervals.get(latest)[1] ? value : latest);
      const span = first === last ? dateLabel(first) : dateLabel(first) + " 至 " + dateLabel(last);
      const undated = candidates.length - [...counts.values()].reduce((sum, count) => sum + count, 0);
      help.textContent = "有记录的日期：" + span + (undated ? " · " + undated + " 篇日期未标注" : "");
    }
  }

  function render() {
    const words = normal(query.value).trim().split(/\s+/u).filter(Boolean);
    const exclusions = new Set(new FormData(form).getAll("exclude-topic"));
    const badge = get("exclude-count");
    badge.hidden = !exclusions.size;
    badge.textContent = exclusions.size ? "已选 " + exclusions.size + " 项" : "";
    const candidates = records.filter(record =>
      (!journal.value || record.journal === journal.value)
      && (!topic.value || record.topic === topic.value)
      && !exclusions.has(record.topic)
      && !(record.clinical && exclusions.has(clinicalTag))
      && record.tier === scope
      && words.every(word => record.searchable.includes(word))
    );
    get("scope-note").textContent = scope === "core"
      ? "人体运动生理、训练适应与身体表现研究。"
      : "含刊外文章。题名显示运动关联，生理或表现结局需进一步查看摘要。";
    updateDates(candidates);

    const rangeMode = form.elements["date-mode"].value === "range";
    get("date-point").hidden = rangeMode;
    get("date-range").hidden = !rangeMode;
    const start = bounds(dateStart.value)?.[0];
    const end = bounds(dateEnd.value)?.[1];
    const matches = rangeMode
      ? candidates.filter(record => matchesDate(record, start, end))
      : candidates.filter(record => !dateSingle.value || record[dateField.value] === dateSingle.value);

    function newest(a, b) {
      return (b[dateField.value] || "").localeCompare(a[dateField.value] || "")
        || collator.compare(a.en, b.en);
    }
    if (sort.value === "grouped") {
      matches.sort((a, b) => compareJournal(a.journal, b.journal)
        || compareTopic(a.topic, b.topic) || newest(a, b));
    } else {
      matches.sort(newest);
    }

    const maxPage = Math.max(1, Math.ceil(matches.length / pageSize));
    page = Math.min(page, maxPage);
    get("result-count").textContent = matches.length.toLocaleString("zh-CN") + " 篇";
    get("pagination").hidden = matches.length <= pageSize;
    get("prev").disabled = page === 1;
    get("next").disabled = page === maxPage;
    get("page-status").textContent = "第 " + page + " / " + maxPage + " 页";
    if (matches.length) {
      renderRows(matches.slice((page - 1) * pageSize, page * pageSize));
    } else {
      const empty = node("div", "empty");
      empty.append(node("strong", "", "没有符合条件的论文"));
      empty.append(node("p", "", topic.value && exclusions.has(topic.value)
        ? "「只看专题」中选中的专题已被排除，可取消对应排除项。"
        : "可以扩大日期范围或清除部分筛选条件。"));
      articles.replaceChildren(empty);
    }
  }

  function refilter() {
    page = 1;
    render();
  }

  function turnPage(offset) {
    page += offset;
    render();
    get("results-heading").focus();
    get("results").scrollIntoView({ block: "start" });
  }

  addOptions(journal, allJournals.sort(compareJournal));
  addOptions(topic, allTopics.sort(compareTopic));
  addExclusion(clinicalTag, clinicalLabel + "（跨专题）");
  for (const name of allTopics) addExclusion(name, name);
  get("total-articles").textContent = records.filter(record => record.tier === "core").length.toLocaleString("zh-CN");
  get("total-journals").textContent = data.journals.length;
  get("updated").textContent = data.updated ? "最近检索 " + data.updated : "暂未收录";
  get("results-heading").tabIndex = -1;
  form.addEventListener("submit", event => event.preventDefault());
  form.addEventListener("change", (event) => {
    if (event.target === dateField) {
      dateSingle.value = dateStart.value = dateEnd.value = "";
    }
    refilter();
  });
  const narrow = matchMedia("(max-width: 800px)");
  const toggle = get("filter-toggle");
  function showFilters(expanded) {
    get("filter-body").hidden = !expanded;
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.textContent = expanded ? "收起" : "展开";
  }
  toggle.addEventListener("click", () => showFilters(get("filter-body").hidden));
  narrow.addEventListener("change", () => showFilters(!narrow.matches));
  showFilters(!narrow.matches);
  query.addEventListener("input", refilter);
  sort.addEventListener("change", refilter);
  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      setScope(tab.dataset.scope);
      refilter();
    });
  }
  get("clear").addEventListener("click", () => {
    form.reset();
    dateSingle.value = dateStart.value = dateEnd.value = "";
    query.value = "";
    setScope("core");
    refilter();
  });
  get("prev").addEventListener("click", () => turnPage(-1));
  get("next").addEventListener("click", () => turnPage(1));
  render();
})();
