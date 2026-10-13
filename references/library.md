# 本地文献库规范

## 目录与职责

```text
literature-library/
  library.json             权威登记记录，脚本管理
  index.md                 自动生成的阅读卡索引
  notes/                   阅读卡，保留各次修订
  records/                 每次入库的 JSON 输入文件
  comparisons/             对比报告与 index.md，阅读代理维护
  glossary/                词汇登记 terms.json、索引 index.md、输入 batches/
  guides/                  中文阅读指南
  recommendations/         已核验推荐或明确标记的候选
  presentations/           按需生成的汇报稿、PPT 与预览
  figures/                 按需绘图的文件、源数据/图源与来源说明
```

库位置取用户指定位置、当前项目此前已确定的库或当前工作目录下的默认库。技能安装目录只含技能文件，不保存用户论文。不要在每次对话随机新建库；换项目需明确选择已有库，否则使用当前项目的库。库内来源路径/版本信息用来重新找到论文，源 PDF 可保留原路径，不要求复制大文件。

也检查环境交付目录中的 `outputs/literature-library/`，遵循 SKILL.md 的选择规则，避免在已存在的库旁再建一个空库。扩展目录按需创建；v1 的 library.json 和旧阅读卡保持兼容。词库详见 [英语阅读规范](english-reading.md)，脚本管理自己的锁和权威 JSON，不改论文登记。指南、推荐、图和汇报之间用真实文件链接关联，代理维护这些报告的索引/链接，不假定 library.py 自动管理它们。

## 脚本调用

以下 `SKILL_DIR` 和 `LIBRARY_DIR` 是说明占位符，执行前换成已确认的绝对路径，参数始终正确引用。脚本仅依赖 Python 3.10+ 标准库，无需第三方安装或 API key。

```bash
python3 "SKILL_DIR/scripts/library.py" init --library "LIBRARY_DIR"
python3 "SKILL_DIR/scripts/library.py" list --library "LIBRARY_DIR"
python3 "SKILL_DIR/scripts/library.py" list --library "LIBRARY_DIR" --query "主题或关键词"
python3 "SKILL_DIR/scripts/library.py" upsert --library "LIBRARY_DIR" --record "LIBRARY_DIR/records/本次记录.json"
python3 "SKILL_DIR/scripts/library.py" check --library "LIBRARY_DIR"
python3 "SKILL_DIR/scripts/library.py" reindex --library "LIBRARY_DIR"
```

登记前阅读卡必须已保存于库内 `notes/`。阅读卡可先用题名或 DOI 命名，入库成功后把返回的 P 编号写入卡片标题。不能把文献读取完成、阅读卡保存完成、登记成功混为一件事。

脚本 `list --query` 做单个子串匹配，不是语义搜索。可使用多个关键词分别查询，结合全部登记记录找同义主题，不能依靠一次关键词查询排除相关文献。

## 结构化记录

下面展示字段格式，不代表真实论文或真实阅读结果。实际填写只取已读材料；不存在的信息用空串/空列表或“未报告”，年份不知道用 null。创新项必须区分主张、证据、判断和核查范围。

```json
{
  "title": "实际论文题名",
  "authors": ["实际作者"],
  "year": null,
  "doi": "",
  "arxiv_id": "",
  "version": "实际版本或未注明",
  "paper_type": "method",
  "evidence_scope": "fulltext",
  "sources": [{"kind": "pdf", "locator": "已读取源文件的绝对路径或真实链接"}],
  "notes_path": "notes/实际阅读卡.md",
  "keywords": ["实际主题", "实际方法"],
  "research_question": "原文研究问题",
  "method": "原文方法概要",
  "framework": "核心模块或研究设计与依赖",
  "data": "数据/样本、版本与划分；没有则不适用",
  "metrics": "指标定义与方向；没有则不适用",
  "results": "核心发现、数字和成立条件；位置见阅读卡",
  "summary": "忠实的研究总结",
  "innovations": [{
    "claim": "作者主张",
    "evidence": "原文证据及页码/章节/图表定位",
    "assessment": "有依据的分析判断",
    "verification": "原文支持；领域新颖性待外部核查"
  }],
  "limitations": ["有来源依据的局限"],
  "anchors": ["真实的章节/页码/图表定位"],
  "related_ids": []
}
```

- `paper_type`：`method` / `empirical` / `theory` / `review` / `other`。
- `evidence_scope`：`fulltext` / `partial` / `abstract` / `notes`。不是论文质量等级。
- `sources[].kind`：`pdf` / `fulltext` / `abstract` / `notes`；可加来源版本、访问日期、文件摘要等字段。
- 完整全文记录必须填写 `anchors`；登记检查只能检查字段，不能证明出处真实或已经阅读全文。
- `related_ids` 指向库内其他 P 编号，用于预印本/发表版、同研究不同报告等关系，不代表独立证据。

## 去重、版本与修订

脚本优先用规范化 DOI，缺少 DOI 时用去掉 v 后缀的 arXiv ID 识别同一身份；`version` 字段保留真实版本。DOI 与 arXiv 分别标识的预印本/发表版不会被静默自动合并，核实后可分别保存、用 `related_ids` 关联。同题名同年份会被拦截，要求核实身份。

- 已有 DOI/arXiv 身份再次入库：返回原 P 编号；内容完全一样时返回 `unchanged`。
- 同一篇无标识符的修订：核实后使用 `--paper-id P0001`。
- 确认同题名同年份但属于不同报告：使用 `--distinct`。这不会绕过完全相同 DOI/arXiv 身份的去重。
- 更新旧记录：先写新阅读卡，例如 `notes/论文标识-分析日期-r2.md`，再登记。脚本拒绝以相同阅读卡路径覆盖旧记录，保留历史记录与旧卡链接。
- 补充新的唯一标识符可以用已核实的 `--paper-id`；不得将一篇的 DOI 换成另一篇的 DOI。更新记录时保留已经核实的元数据。

原文不同版本的结果和创新主张可能变化，对比报告应注明自己使用哪一版。不要只更新记录的版本字符串而继续使用旧版结果。

## 对比报告与恢复

报告保存为 `comparisons/日期-主题-参与编号.md`，同日重做可加修订序号。维护 `comparisons/index.md`，列日期、主题、参与编号、版本及报告链接；脚本只生成论文 `index.md`，不生成语义对比。

写入采用锁文件避免两个登记进程同时覆盖，JSON 采用临时文件替换。遇到锁冲突稍后重试，不自动移除正在使用的锁；中断留下的锁需确认没有写入进程再清理。登记 JSON 是权威来源，索引生成失败时先检查 JSON 的实际状态，运行 `reindex` 恢复，不能误报完全未入库。未知 schema 或损坏记录时保留原库，停止写入并报告具体问题。

没有 Python 时可以按上述结构手工维护：先检查重复与现有编号，保存阅读卡再写 JSON，最后重建索引；清楚说明未运行脚本验证。如果环境只支持聊天而不能写文件，交付可复制的阅读卡和对比内容，并说明未持久保存，不能承诺后续会自动记住。
