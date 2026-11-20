(() => {
  "use strict";

  const get = (id) => document.getElementById(id);
  const data = JSON.parse(get("dataset").textContent);
  const journal = get("journal");
  const topic = get("topic");
  const dateField = get("date-field");
  const dateStart = get("date-start");
  const dateEnd = get("date-end");
  const query = get("query");
  const sort = get("sort");
  const articles = get("articles");
  const tabs = [...document.querySelectorAll("button[data-scope]")];
  const pageSize = 20;
  const collator = new Intl.Collator("zh-CN", { numeric: true, sensitivity: "base" });
  const journalRank = new Map(data.journals.map((name, index) => [name, index]));
  const topicRank = new Map(data.topics.map((name, index) => [name, index]));
  const allTopics = [...new Set(data.records.map(record => record.topic))];
  const allJournals = [...new Set([...data.journals, ...data.records.map(record => record.journal)])];
  let page = 1;
  let scope = "";

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

  function render() {
    const from = dateStart.value;
    const to = dateEnd.value;
    const invalid = Boolean(from && to && from > to);
    get("date-error").hidden = !invalid;
    dateStart.setAttribute("aria-invalid", String(invalid));
    dateEnd.setAttribute("aria-invalid", String(invalid));
    get("date-help").textContent = dateField.value === "seen"
      ? "按系统首次收录的日期筛选。"
      : "按数据库提供的发表日期筛选。";

    const words = normal(query.value).trim().split(/\s+/u).filter(Boolean);
    const matches = invalid ? [] : records.filter(record =>
      (!journal.value || record.journal === journal.value)
      && (!topic.value || record.topic === topic.value)
      && (!scope || record.focused === (scope === "focus"))
      && matchesDate(record, from, to)
      && words.every(word => record.searchable.includes(word))
    );
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
      empty.append(node("strong", "", invalid ? "请检查日期范围" : "没有符合条件的论文"));
      if (!invalid) empty.append(node("p", "", "可以扩大日期范围或清除部分筛选条件。"));
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
  get("total-articles").textContent = records.length.toLocaleString("zh-CN");
  get("total-journals").textContent = data.journals.length;
  get("updated").textContent = data.updated ? "最近检索 " + data.updated : "暂未收录";
  get("results-heading").tabIndex = -1;
  get("filters").addEventListener("submit", event => event.preventDefault());
  get("filters").addEventListener("input", refilter);
  query.addEventListener("input", refilter);
  sort.addEventListener("change", refilter);
  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      setScope(tab.dataset.scope);
      refilter();
    });
  }
  get("clear").addEventListener("click", () => {
    get("filters").reset();
    query.value = "";
    setScope("");
    refilter();
  });
  get("prev").addEventListener("click", () => turnPage(-1));
  get("next").addEventListener("click", () => turnPage(1));
  render();
})();

