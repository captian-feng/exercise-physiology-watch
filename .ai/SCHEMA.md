# Contribution Schema

每个 JSON 对象只对应一篇论文，字段固定如下：

~~~json
{
  "status": "new",
  "pmid": "",
  "doi": "",
  "title_en": "",
  "title_zh": "",
  "abstract_en": "",
  "abstract_zh": "",
  "journal_en": "",
  "journal_zh": "",
  "article_type": "",
  "topic": "",
  "official_url": "",
  "backup_url": "",
  "source": [],
  "first_seen": "",
  "published_online": "",
  "processed_by": "",
  "processed_at": "",
  "translation_source": "",
  "translation_status": "",
  "notes": ""
}
~~~

status 只能是：new、updated、title_translation、abstract_translation、metadata_fix、skipped-existing、duplicate、needs-review、source-missing。

