# 英语阅读、词库与指南

## 术语如何选择和呈现

默认提取理解这篇论文必需的专业概念、方法名、专业缩写和在本方向有特定含义的词组。先抓影响问题、方法与结果理解的词，不把所有生词或通用英语堆成单词表。用户可要求扩大范围。只提取已读正文实际出现的表达，标题/摘要级读取应标注范围。

用 `scripts/glossary.py lookup` 或读取词库先识别已见术语。中文笔记/指南第一次使用本次新概念时写“中文（English，缩写）”，并在新术语表列英文、中文、通俗解释、论文中的用途和原文位置。后续使用中文或必要缩写；旧词不重新逐词解释，但保留科学表达所必需的符号。默认不修改原 PDF。用户明确要求 PDF 批注时使用相应 PDF 工具制作副本，确认工具支持后才能声称已标注。

去重依赖持久词库，不依赖聊天记忆。已有词通常只记录新增出处，附词库查询链接；用户要求复习/再次解释时可重新展开。`seen` 是已出现，`mastered` 是用户明确确认已掌握，`review` 是待复习；出现次数不会自动改成掌握。默认旧词去重包括 seen/review，但用户要求复习或卡住某一词时主动解释。

## 词库与确定性操作

每个文献库维护自己的 `glossary/terms.json` 和自动生成的 `glossary/index.md`，稳定 T 编号。跨库共享须采用用户指定的同一库或明确迁移，不能自动扫描私人目录。脚本依赖 Python 3.10+ 标准库，只负责登记/去重，不从 PDF 自动提词；提词、译义和语境核实由模型完成。

术语匹配使用规范英文/已核实别名 + 稳定词义标签 `sense`。脚本只规范大小写、空白和常见连字符；不猜测词干、同义词或复数。缩写、全称、复数、译名对应须先核实后显式加入 `aliases`。例如 `KF` 是缩写别名，不能把全文出现的字母 `K` 无条件视为它。相同缩写有不同含义时建立不同 sense；查询返回多个词义，不能随便选择。同词义匹配多个条目会阻止写入，需要先核实，不能强行合并。首次建立的标准释义保持不变，后续特殊用法写在有出处的 `context`；需要修订标准释义时保留备份并明确修订理由。

先将论文入库得到 P 编号，再保存 `glossary/batches/日期-P编号.json`：

```json
{
  "paper_id": "P0001",
  "terms": [{
    "term": "Kalman filter",
    "sense": "state-estimation",
    "chinese": "卡尔曼滤波器",
    "aliases": ["KF"],
    "definition": "用动态模型预测状态，再利用观测修正估计的递推方法。",
    "anchors": ["此处须填该篇真实页码/章节"],
    "context": "此处须填该篇的具体用途；示例不是论文证据"
  }]
}
```

以下路径占位符执行前换成实际已确认路径：

```bash
python3 "SKILL_DIR/scripts/glossary.py" lookup --library "LIBRARY_DIR" --query "KF"
python3 "SKILL_DIR/scripts/glossary.py" ingest --library "LIBRARY_DIR" --batch "LIBRARY_DIR/glossary/batches/实际批次.json"
python3 "SKILL_DIR/scripts/glossary.py" status --library "LIBRARY_DIR" --term-id T0001 --status mastered
python3 "SKILL_DIR/scripts/glossary.py" check --library "LIBRARY_DIR"
python3 "SKILL_DIR/scripts/glossary.py" reindex --library "LIBRARY_DIR"
```

lookup 无词库时返回空列表、不创建文件。ingest 按需建立词库；返回 `new_terms` 与 `reused_terms`，最终新词表只展开 new_terms，重复词记录出处。同一批重复执行不重复建立词条/出处，不改掌握状态。旧卡和旧 library.json 无需迁移。词库索引失败时 JSON 已可能保存，检查实际状态后 reindex；遇到锁或损坏数据停止写入，不删除活跃锁、不清空库。

## 阅读指南

用 [阅读指南模板](../assets/reading-guide.md)，以当前论文为主，不再复制完整阅读卡。默认给约 30–45 分钟的首轮理解路线，时长是建议估计。用户可以指定 15 分钟快读、深入公式或零基础。

- 先讲清这篇在解决什么问题、为什么原方法不够、核心思路和成立边界。英文标题保留，解释使用中文。
- 列理解本篇必需的背景及一句话桥接，不假定用户已掌握相关数学。
- 依据实际章节/图表安排阅读顺序，标记必读/可略读/第二轮深读。每步给位置、要回答的问题和应得到的结论。
- 对核心公式给符号、作用和与前后步骤的关系，先讲概念再讲推导。区分术语 innovation（观测新息）和论文创新性等易混用法。
- 难句用户需要时按“句子主干、逻辑连接、语境含义”解释；不默认逐页全译。
- 给少量自测题和需要警惕的误读，把“不会英语”和“缺少方法背景”分开帮助。

指南存 `guides/日期-P编号.md`，修订另存新文件。词库条目链接使用真实相对路径和 T 编号锚点，首次术语表从本次登记结果生成。阅读卡链接指南及词库，本次只有旧词则写“本次无新词”，不凑数。
