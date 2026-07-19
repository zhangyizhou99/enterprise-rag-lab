# 工程复盘与简历证据

这是一份持续更新的工程记录，用于复习设计思路、准备面试和生成真实的简历素材。它不替代开发计划，而是回答以下问题：

- 实际遇到了什么问题？
- 根因是什么，如何验证？
- 为什么选择当前方案？
- 还有什么没有完成？
- 哪些结果可以写进简历，哪些不能夸大？

记录原则：只写可以通过代码、测试、CLI 输出或数据库查询复现的事实。合成 fixture、公开语料和真实企业数据必须明确区分。

## 当前可验证快照

记录日期：2026-07-19。

当前阶段：125 份 FastAPI Markdown 已完成批量入库、清洗、chunker 0.4.0 版本化 Chunk 和 SQLite FTS5 BM25 索引；全量语料暴露的仅标题 Chunk、超长代码 Chunk 与 E5 token 超限问题已处理。主库每份文档最新版本共 127 份、1,362 个无截断 Embedding，并已同步到版本化 Qdrant embedded 快照。30 条评测问题、42 条 Chunk judgment 已完成 `approved = 30/30` 的人工审核。BM25 Top-20 与向量 Top-20 的固定 $k=60$ RRF、章节相邻上下文扩展及四路正式消融已经完成。PDF parser 0.3.0 新增原生文本表格的行列识别、逐页 bbox 和确定性跨页合并；主数据库、Chunk、Embedding 与 Qdrant 快照尚未按新 parser 重建。

验证命令：

```powershell
.\.venv\Scripts\python.exe -m pytest .\tests -q
```

当前结果：`55 passed`，`pip check` 无依赖冲突，本次触及的 Python 文件编辑器诊断为 0。

主数据库 `data/state/ingestion.sqlite3` 当前使用公开语料和合成 fixture，只代表教学项目的阶段性规模：

| 数据 | 数量 |
|---|---:|
| documents | 127 |
| document_versions | 129 |
| parsed_blocks | 8,090 |
| ingestion_runs | 754 |
| cleaning_versions | 131 |
| cleaned_blocks | 7,338 |
| cleaning_rule_hits | 1,060 |
| chunking_versions | 383 |
| chunks | 4,013 |
| keyword_index_versions | 380 |
| chunk_fts | 3,891 |
| embedding_versions | 254 |
| chunk_embeddings | 2,675 |
| vector_index_versions | 1 |
| vector_index_members | 127 |

这些表包含旧版与新版历史记录。最近一次清洗的格式级结果如下：

格式级结果：

| 格式 | 样例 | 原始块 | 清洗块 | 删除块 | 修改块 | 当前结论 |
|---|---|---:|---:|---:|---:|---|
| Markdown | FastAPI CORS | 39 | 39 | 0 | 1 | 保留全部正文和标题路径，仅规范空白 |
| DOCX | 合成 noisy postmortem fixture | 20 | 12 | 8 | 0 | 删除明确噪声，保留正文和表格结构 |
| PDF | RFC 9112 | 46 | 46 | 0 | 46 | 保留 1 至 46 页，移除跨页高频页眉页脚并规范空白 |

注意：DOCX 样例是为了回归测试而生成的合成 fixture，不能描述为真实企业文档。125 个 Markdown 已全部入库；6 个 PDF 原始文件中当前只有 RFC 9112 进入主数据库。

最新分块与索引结果：

| 格式 | 最新 Chunk 数 | 最小字符 | 平均字符 | 最大字符 | 索引状态 |
|---|---:|---:|---:|---:|---|
| Markdown | 1,222 | 6 | 319 | 891 | 125 份均为 `keyword_indexed` |
| DOCX | 6 | 64 | 138 | 208 | `keyword_indexed` |
| PDF | 134 | 219 | 733 | 900 | `keyword_indexed` |

物理表保留历史版本，不能直接当作当前可检索规模。当前每份文档最新索引共 127 份、1,362 个 Chunk，其中 Markdown 为 125 份、1,222 个；`chunk_fts = 3,891` 和 `chunk_embeddings = 2,675` 均包含历史重建版本。BM25 SQL 按文档过滤到最新 `keyword_index_versions`，Qdrant 当前 collection 则只包含最新 1,362 点。Markdown 最短项是独立 HTML 闭合标签 `</div>`，不是孤立标题，但缺少语义价值，已进入清洗坏例队列。

## 当前数据流与输入输出

```text
原始文件
  -> Parser
  -> ParseResult + ParsedBlock
  -> documents / document_versions / parsed_blocks
  -> CleaningService
  -> CleanResult + CleaningRuleHit + CleaningStats
  -> cleaning_versions / cleaned_blocks / cleaning_rule_hits
    -> ChunkingService
    -> chunking_versions / chunks
    -> FTS5 trigram keyword index
    -> BM25 Top-K + 来源定位
    -> EmbeddingService / embedding_versions / chunk_embeddings
    -> Qdrant 不可变快照
    -> E5 Query Embedding / cosine Top-K + 来源定位
    -> BM25 Top-20 + Vector Top-20
    -> RRF Top-5 + 两路排名/分数/来源快照
    -> 同章节前后邻居 + 字符预算 + 跨锚点去重
    -> anchor / expanded_chunks / context_text
    -> 后续 rerank
```

### 解析层

输入：Markdown、DOCX、PDF 文件路径。

输出：统一的 `ParseResult`，其中每个 `ParsedBlock` 保留来源定位信息：

- Markdown：标题层级 `heading_path`。
- PDF：页码 `page_number`；原生文本表格另保存来源页、逐页 bbox、表头、行列数和识别器版本。
- DOCX：块类型、标题层级、样式、表格序号和 section 信息。

解析块是来源可定位单元，不是最终向量 Chunk。Chunk 还需要考虑长度、语义边界、父子关系和相邻上下文，不能在解析阶段混为一谈。

### 清洗层

输入：数据库中的不可变 `parsed_blocks`。

输出：

- `cleaned_blocks`：后续分块和索引使用的清洗副本。
- `cleaning_rule_hits`：规则、动作、源块序号、修改前文本和修改后文本。
- `cleaning_versions`：清洗器版本、规则集版本和统计信息。

清洗不使用 LLM 改写正文，也不覆盖原始块。它只执行可测试、可重放的确定性规则。

## 真实问题时间线

| 问题 | 表面现象 | 根因 | 处理结果 | 状态 |
|---|---|---|---|---|
| 模块无法导入 | `No module named enterprise_rag_lab` | 激活的是 `hello-agents/.venv`，且 `src` 布局项目未安装 | 建立项目级 `.venv` 并执行 `pip install -e ".[dev]"` | 已解决 |
| 输出无法直观看到 | 入库成功但只能知道 run 状态 | 最初缺少只读检查接口 | 已增加查询 CLI，但大文档 JSON 仍不易阅读 | 部分解决，界面与分页待做 |
| 旧 `.doc` 无法解析 | `python-docx` 读取失败 | `.doc` 是旧二进制格式，不是 OOXML DOCX | 返回结构化转换错误并持久化失败 run | 部分完成，待 LibreOffice 转换 |
| SQLite 临时文件被锁 | Windows 删除测试数据库时报 `WinError 32` | `with sqlite3.Connection` 只提交或回滚，不会自动关闭连接 | 用自定义 context manager 显式 commit、rollback、close | 已解决 |
| 表格结构被空白规则破坏 | DOCX 表格的制表符被转为空格 | 通用空白正则没有区分块类型 | 为 table 保留 `\t`，为 code 保留缩进 | 已解决 |
| “删除 8 块”被误解为“8 块重复” | 统计数字无法解释删除原因 | 聚合统计没有展示规则构成 | 使用 rule hit 逐条回溯源块 | 已澄清 |
| PDF 审计输出过大 | `inspect-cleaning` 输出约 73 KB | PDF 每页是一个大块，46 页都记录完整 before/after | 已确认根因；后续需要审计摘要或分页 | 待优化 |
| PDF 页眉页脚仍存在 | 每页都有 RFC 标题和 `Page N` | PDF 只有整页文本，没有独立 header/footer 块 | 对页首/页尾三区做跨页频率统计，并归一化 `Page N` | 已解决并回归验证 |
| PDF 跨页表格错序和拆断 | RFC Table 2 的 `chunked` 在第 35 页，其余行在第 36 页，参考文献被提到续表之前 | `pypdf.extract_text()` 只有页级字符串，不提供表格边界、行列或跨页关系 | 使用 pdfplumber 识别表格 bbox/逻辑行，从重复横向起点恢复列；仅在相邻页、页底/页顶、表头和列起点同时一致时合并 | 识别层已解决；长表按行分块待做 |
| DOCX 表格顺序错误 | 表格统一出现在所有段落之后 | parser 分别遍历 `paragraphs` 和 `tables` | 使用公开 `iter_inner_content()` 按源顺序读取 | 已解决并提升 parser version |
| PDF 出现 13 字符碎片 Chunk | 逐页贪心装箱留下过短尾段 | 最后一组超过上限后被单独刷新 | 在同页内对最后两组按行/句边界再平衡 | 已解决，最小值提升到 251 |
| BM25 正文排序不理想 | `message parsing` 的正文页排在摘要和目录之后 | 关键词完全匹配但缺少语义、章节角色和重排信号 | 保留为可解释基线；已完成向量/RRF 对照，仍待上下文扩展与 rerank | 部分解决 |
| 批量引用 URL 少了 `docs/zh` | 本地相对路径被直接拼到仓库根 URL | 忽略了数据集的 sparse checkout 前缀 | 按 `docs/zh` 来源映射重跑，稳定 ID 保证不新增文档 | 已解决 |
| Markdown 出现 2 字符 Chunk | 独立短标题不能跨 `heading_path` 合并 | 标题边界优先，但缺少“标题附着到子节”的策略 | 仅将纯标题草稿附着到同节或子节首块；19 个标题块降为 0，最小值由 2 提升到 14 | 已解决并回归验证 |
| Markdown 出现 3,585 字符 Chunk | 超长 fenced code 保持原子性 | 代码完整性优先于普通文本上限 | 按换行优先、硬边界兜底拆分，并在拆分片段前后 flush；7 个超限块降为 0，最大值降到 1,187 | 已解决并回归验证 |
| Embedding 依赖首次未安装完成 | 默认源下载 `transformers` 到 6.8/11.6 MB 时取消 | PyTorch 与 Transformers 依赖体积大，初次下载速率约 42 KB/s | 改用 PyPI 镜像完成底层依赖，再用 `--no-deps` 安装 596 KB 顶层 wheel；`pip check` 无冲突 | 已解决 |
| Hugging Face 主站不可达 | PowerShell 和页面工具都无法读取模型配置 | 当前网络不能直连 `huggingface.co` | 使用可达镜像下载模型，471 MB 权重约 59 MB/s；记录解析后的 commit 而不是只记录 `main` | 已解决 |
| 字符上限不等于模型 token 上限 | 1,313 个 Chunk 中有 6 个达到 517 至 572 tokens | 1,200 字符不能保证低于 E5 的 512-token 上限 | 对 900/850/800 三档全库模拟；选择碎片增量最小且超限为 0 的 900，将最大值降到 488，并默认拒绝落库截断向量 | 当前语料已解决；未来分布仍由存储前防线兜底 |
| Qdrant 临时目录删除失败 | 查询成功后清理 `storage.sqlite` 报 `WinError 32` | 先 `delete_collection()` 会把对象移出 QdrantLocal 注册表，随后 `client.close()` 无法遍历并关闭该 collection 的 storage | 改用不可变 collection，不执行 delete/recreate；始终先关闭整个 client，再清理目录 | 已解决并用真实 embedded 冒烟验证 |
| Markdown 出现 6 字符 Chunk | chunker 0.4.0 重建后最短值由 14 降到 6 | 更严格上限改变相邻装箱，FastAPI 首页的独立 `</div>` 被单独刷新 | 确认块类型为 paragraph、孤立标题数仍为 0；暂不增加宽泛 HTML 删除规则 | 已定位，待清洗坏例规则 |
| `OAuth2 密码` 无结果 | 单词查询能命中，但组合查询为空 | 旧版 `_fts_query()` 将完整输入包装成精确短语 | v0.2.0 改为去重字符 trigram `OR` 并加入回归；更精细的查询模式仍待实现 | 原故障已解决 |
| 同内容跨格式可能重复索引 | Markdown 转 DOCX 后可能同时进入索引 | 文件格式不同但语义内容相同 | fixture 与默认问答语料隔离，后续增加 canonical 去重策略 | 未完成 |
| RRF 未超过向量基线 | RRF Hit Rate/Recall/MRR 为 0.833/0.733/0.672，向量为 0.867/0.767/0.692 | 固定 $k=60$ 时，两路中等排名的重叠候选可压过仅一路高排名的正确候选 | 保留负向消融和逐题 provenance；相邻扩展已单独评估，后续继续做 rerank | 已定位，部分后续完成 |
| 上下文扩展首版没有新增命中 | 完全相同 `parent_id` 的 depth=1 扩展后，证据指标与 RRF 相同 | `parent_id` 绑定完整标题路径，父标题与直接子标题、同父兄弟标题会得到不同 ID | v0.2.0 改用标题父子/同父兄弟结构关系，同时禁止跨 PDF 页 | 已解决并完成正式消融 |
| 扩展上下文膨胀 | 证据 Recall 提升到 0.883，但平均每题新增 5.77 个 Chunk，95.4% 扩展项无 judgment | 相邻关系只能提供结构先验，不能判断当前问题下的语义相关性；42 条 judgment 也不是全语料穷举标签 | 单列扩展证据指标、字符成本与 `unjudged` 比例，不把未标注项叫噪声；交给后续 reranker 压缩 | 已量化，待 rerank |
| Windows CLI 无法打印 emoji | `list-chunks` 在 GBK stdout 遇到锁形 emoji 时抛 `UnicodeEncodeError` | `ensure_ascii=False` 生成的 Unicode 文本超出终端编码字符集 | 输出前检测 stdout 可编码性，不可编码时退回合法 JSON Unicode 转义 | 已解决并用 GBK 模拟回归 |

## 技术难点与决策

### 1. `src` 布局与独立虚拟环境

症状：终端显示 `(.venv)`，但运行 `python -m enterprise_rag_lab` 仍然报模块不存在。

关键判断：虚拟环境名称相同不代表环境相同。需要检查解释器绝对路径：

```powershell
(Get-Command python).Source
```

根因：当时实际解释器位于另一个工作区的 `<workspace>\hello-agents\.venv`。同时项目使用 `src/enterprise_rag_lab` 布局，源码目录不会仅因为当前目录正确就自动进入 Python 导入路径。

方案：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

为什么使用 editable install：它保留标准包发现行为，同时源码修改立即生效，比长期依赖临时 `PYTHONPATH=src` 更稳定。

面试表达：排查 Python 导入问题时，先确认解释器路径、包安装状态和项目布局，不只看 shell 提示符。

### 2. 多格式解析必须收敛到统一契约

不同格式天然提供不同定位能力：Markdown 有标题树，PDF 有页码，DOCX 有样式、section 和表格。若每种格式直接输出字符串，后续检索引用就无法统一。

当前决策：Parser 统一输出 `ParseResult` 和 `ParsedBlock`，同时允许格式特有定位数据保存在标准字段和 metadata 中。

已验证能力：

- CORS Markdown 的正文块可以定位到 `CORS（跨域资源共享） > 源`。
- RFC PDF 清洗后仍保留连续的 1 至 46 页页码。
- RFC PDF 共识别 3 张逻辑表和 4 个页面片段；Table 2 自动合并为第 35 至 36 页、3 列 8 行，并保留两页 bbox。
- DOCX 能识别标题、段落、表格、页眉和页脚。

DOCX 顺序修复：parser 使用 `python-docx` 的公开 `iter_inner_content()` 接口按段落和表格的源顺序遍历。测试夹具中的表格现在位于“3. Environment variables”和“4. Deployment steps”之间；主数据库 noisy DOCX 的 Timeline 标题、表格和 Root cause 序号为 `6 -> 7 -> 8`，表格标题路径为 `2. Timeline`。

### 3. 幂等入库、版本和失败审计

企业知识库会重复执行入库。如果每次运行都生成新文档，就会污染索引和评测结果。

当前 ID 设计：

- `document_id`：由规范化本地路径稳定生成。
- `canonical_id`：优先由来源 URI 生成，否则使用内容哈希。
- `version_id`：由 document ID、内容 SHA-256 和 parser version 生成。
- `run_id`：每次执行使用 UUID，保留独立运行记录。

效果：同一路径和同一内容重复入库复用文档与版本身份，但每次运行仍可审计。解析失败也写入 `ingestion_runs`，而不是只在终端打印异常。

仍需完善：跨路径、跨格式的同内容识别还没有形成完整的 canonical 策略。

### 4. SQLite 上下文管理的 Windows 文件锁

错误假设：`with sqlite3.connect(...) as connection` 离开作用域后会关闭连接。

实际行为：标准库 Connection 的上下文管理只负责事务提交或回滚，不保证关闭。Windows 对打开文件的删除限制更严格，因此临时测试数据库在清理时触发 `WinError 32`。

修复：Store 的 `_connect()` 改为自定义 context manager：

```text
成功 -> commit -> close
异常 -> rollback -> close -> 重新抛出
```

验证：相同端到端测试现在可以在完成查询后立即删除临时目录。

面试表达：这不是 SQLite 查询逻辑错误，而是资源生命周期错误；测试环境的临时文件清理帮助暴露了生产中可能累积的连接泄漏。

### 5. 原始数据不可变与可回放清洗

如果直接覆盖解析文本，就无法回答“某条正文是解析丢失，还是被清洗规则删掉”。这会让检索坏例无法定位。

当前方案：

- `parsed_blocks` 永久保存 parser 输出。
- `cleaned_blocks.source_ordinal` 指回源块。
- 每次规则命中记录 before/after 和 action。
- `cleaning_id` 由 source version、cleaner version、rule set version稳定生成。

因此同一输入与同一规则集可以确定性重放；规则升级则生成不同版本身份。

### 6. 规则顺序会改变审计语义

noisy DOCX 删除了 8 块，但只有 4 块是完全相同的文本：

```text
source ordinal 2, 3, 14, 15
文本均为 DRAFT - DO NOT DISTRIBUTE
```

这 4 块记录为 `drop_distribution_label`，而不是 `deduplicate_exact_paragraph`。原因是规则先判断“该内容是否应该整体删除”，再对仍有业务价值的普通段落去重。

如果先去重，会删除其中 3 条却留下 1 条草稿标签。最终块数可能只差 1，但语义是错误的。这说明清洗不能只看删除率，还要检查规则命中原因。

另外 4 个删除项分别是：

- 1 个下载提示。
- 1 个浏览器媒体占位提示。
- 1 个 DOCX 页眉。
- 1 个 DOCX 页脚。

### 7. 通用空白清洗会误伤结构

第一版规则将所有水平空白压缩为一个空格，导致 DOCX 表格中的 `\t` 列分隔符消失。修复后按块类型处理：

- code：只清理首尾换行，保留缩进。
- table：逐单元格规范空白，保留制表符列边界。
- 普通文本：规范普通空格、换行和不换行空格。

真实 CORS 回归测试要求清洗前后都保留 39 块，并包含 `CORSMiddleware` 和“源”标题路径，用来防止规则误删正文。

### 8. PDF 表格识别与页眉清洗必须协同

DOCX parser 会把页眉页脚标记为独立 block type，因此可以安全删除。PDF 没有天然的 header/footer 或 table 语义；parser 0.3.0 只对原生文本 PDF 增加坐标表格识别，普通页面仍沿用 pypdf 文本提取。

RFC 9112 当前结果：

- parser 输出 53 个来源块，包含 3 张逻辑表；清洗后保留 51 个，删除的 2 个都是表格切段后只剩模板内容的纯页眉/页脚块。
- 46 个页码全部保留且连续。
- 46 页均命中 `drop_repeated_pdf_boilerplate`，重复的 RFC 页眉、页脚和 `Page N` 行已移除。
- 共识别 3 张逻辑表、4 个页面表片段；跨页 Table 2 为 3 列 8 行，表格文本不包含第 36 页参考文献。
- 正文中的 `Message Parsing` 等验证锚点仍然存在。

不能直接无条件删除每页首尾固定行，因为封面、目录和章节换页可能具有不同布局。当前实现采用：

1. 按页拆行，只检查前三和后三个非空行。
2. 对 `Page N` 后缀做受约束归一化，不使用宽泛数字正则。
3. 分别统计页首和页尾，并按模板身份跨两侧聚合，兼容 pypdf 与坐标提取顺序差异。
4. 仅当命中至少 3 页且覆盖不少于 60% 页面时才删除。
5. 每次删除仍记录页码、原文和规则。
6. 用合成页面验证正文中部重复行不会被删，并用真实 RFC 验证 46 页连续、正文锚点保留。

表格续接要求前一片段是前页最后一张表、后一片段是后页第一张表，且分别位于页底和页顶，同时表头及标准化列起点一致；不会仅凭相邻页强行拼接。剩余限制：扫描件、复杂并排或旋转表格尚未覆盖；列恢复是确定性坐标启发式而非视觉模型。parser metadata 已保存跨页范围，但当前 Chunker 仍把 table 原子化，未完成按行切分和跨页范围传播。

### 9. 数据来源与重复语料治理

真实公开 DOCX 比 Markdown 和 PDF 更难稳定获取，也常缺少清晰许可。当前选择是：

- 公开 FastAPI Markdown 使用固定 commit，保证可复现。
- PDF 保存来源和 SHA-256。
- 合成 DOCX 只验证结构与规则，明确标记为 fixture，不进入默认问答索引。
- 来源信息不完整的旧 `.doc` 只做本地兼容性验证。

`scripts/generate_docx_fixtures.py` 目前仍能把 5 份 FastAPI Markdown 复制为 DOCX。它们不能与原 Markdown 同时进入默认索引，否则会造成跨格式语义重复。进入批量索引前应移除这项默认生成行为或增加明确的 fixture 开关。

### 10. 旧版 `.doc` 转换是受控流程，不是静默跳过

`python-docx` 只能处理 DOCX，不能直接读取旧版 Word 二进制 `.doc`。当前在转换器缺失时返回 `legacy_doc_conversion_required`，并把 LibreOffice 安装和转换建议写进错误信息。

未完成事项：LibreOffice 尚未成功安装，转换产物哈希、转换器版本和原始格式映射也尚未落库。因此目前只能声称“支持检测和可审计失败”，不能声称“已经支持 `.doc` 入库”。

### 11. 分块不是固定字符切片

当前 chunker 0.4.0 以 800 字符为软目标、900 字符为普通文本硬上限，但边界优先级高于凑满长度：

- 标题路径变化必须断开，避免两个章节混入同一 Chunk。
- PDF 页码变化必须断开，保证引用只指向单页。
- table 保持原子性；若超过上限则显式标记 `oversized_atomic_block`。
- 未超限 code 保持完整；超长 code 优先在后半段的最后一个换行处切分，无可用换行时才按字符上限兜底，并用 `split_code_block` 标记。
- 普通长文本依次在提取行、句子和单词边界拆分，不直接从字符串中间截断。
- 每个 Chunk 保存 `source_ordinals`、`parent_id`、`previous_chunk_id` 和 `next_chunk_id`。

这意味着 parser 0.3.0 的“跨页表格已识别”不等于“超长表格检索已完成”。当前长表仍可能形成 `oversized_atomic_block`，且 Chunk 的 `page_end` 尚未读取 table metadata；下一步需要按完整行分块、重复表头并传播逐页来源。

第一次真实运行时，RFC 9112 的 107 个 Chunk 中有 8 个短于 200 字符，最短只有 13 字符。根因是贪心装箱把页尾剩余行单独作为一个 Chunk。chunker 0.2.0 在同页、同源块范围内重新平衡最后两组，Chunk 数仍为 107，平均值仍为 919，最大值仍为 1,200，最小值提升到 251；没有跨页合并。

全量 Markdown 又暴露两个边界。第一，父标题后立即进入子标题时，父标题会形成只有 2 至 10 字符的独立 Chunk。chunker 0.3.0 只在前一草稿仅含 heading、下一草稿位于同一标题路径或其子路径、页边界一致且合并后不超上限时向后附着；历史版本中的 19 个仅标题 Chunk 在最新版本降为 0。第二，7 个 fenced code 超过 1,200 字符，其中最长 3,585。新版本将它们拆成 19 个独立代码 Chunk，在每个片段加入前后都 flush，避免吸收相邻正文；19 个片段均保留原 `source_ordinal`，且 `block_types` 严格为 `code`。

真实 E5 运行又证明字符数不是 token 数。1,200 字符版本有 6 个普通段落或 PDF 页 Chunk 超过 512 tokens。对全库清洗块做不落库模拟后，900/850/800 三档都能把超限数降为 0；900 只把最新 Chunk 从 1,313 增加到 1,362，少于更严格阈值带来的碎片，因此选择 900。重建后 P95 为 379、P99 为 451、最大为 488。这个阈值是当前中英文语料的经验校准，不是对任意未来文本的 token 保证；`EmbeddingService` 因此默认在任何超限时整份文档失败且不落库，只有显式 `--allow-truncation` 才可覆盖。

### 12. 中英文关键词索引的 tokenizer 取舍

SQLite FTS5 的 `unicode61` 适合英文单词，但当前语料同时包含没有空格分词的中文。环境探测确认 SQLite 3.50.4 支持 `trigram` tokenizer，并分别命中“跨域资源”和 `message parsing`，因此第一版使用 trigram 加 `bm25()` 作为统一、零外部服务的关键词基线。

索引版本绑定 `chunking_id + indexer_version + tokenizer`；重复执行复用同一个 `index_id`。搜索只查询每份文档最新索引，旧 Chunk 和旧索引继续保留用于回放。

局限：trigram 更接近字符子串检索，不等同于语言学分词；短于 3 字符的查询当前拒绝执行。后续需要通过同一评测集比较 trigram BM25、语言分词 BM25、向量召回和混合召回，不能只凭示例观感决定方案。

### 13. 当前 Top-K 关键词召回与 BM25 排序链路

`search` 命令只执行关键词支路；项目另有独立向量支路和 RRF 融合，但尚无 rerank：

```text
CLI: search <query> --limit K
    -> KeywordSearchService.search(query, K)
    -> _fts_query(): 规范空白，生成去重字符 trigram 并以 OR 连接
    -> SQLiteIngestionStore.search_keyword(fts_query, K)
    -> chunk_fts MATCH: 筛选匹配候选
    -> 过滤到每份文档最新 keyword_index_versions
    -> bm25(): 对候选做一阶段相关性排序
    -> ORDER BY raw_score ASC
    -> LIMIT K
    -> enumerate(..., start=1): 生成 rank 1..K
```

因此 `search --limit 3` 不是“先召回很多候选再重排为 Top-3”，而是让同一条 SQL 在 BM25 排序后直接返回前三条。`hybrid-search` 才会分别扩大到两路候选池并执行 RRF；两条命令都没有 rerank model 或 rerank score。

#### BM25 解决什么问题

BM25 是基于词项统计的稀疏检索排序函数。它不理解向量语义，而是在已匹配的文档中综合考虑以下信号：

- 词频：查询词或短语在当前 Chunk 出现越多，通常越相关，但收益会逐渐饱和，不会简单线性增长。
- 逆文档频率：只在少量 Chunk 中出现的词区分度更高；到处都出现的常见词贡献较低。
- 文档长度归一化：同样命中一次时，短而聚焦的 Chunk 通常比很长的 Chunk 更相关。
- 字段权重：标题或标题路径中的命中可以比正文命中更重要。

常见 BM25 形式为：

$$
\operatorname{BM25}(D,Q)=\sum_{q_i \in Q}\operatorname{IDF}(q_i)
\frac{f(q_i,D)(k_1+1)}
{f(q_i,D)+k_1\left(1-b+b\frac{|D|}{\operatorname{avgdl}}\right)}
$$

其中：

- $D$ 是当前 Chunk，$Q$ 是查询。
- $f(q_i,D)$ 是查询词项或短语在 Chunk 中的加权出现次数。
- $|D|$ 是当前 Chunk 的 token 数，$\operatorname{avgdl}$ 是索引内平均 Chunk 长度。
- $\operatorname{IDF}(q_i)$ 衡量词项稀有程度。
- $k_1$ 控制词频饱和速度，$b$ 控制长度归一化强度。

SQLite FTS5 将 $k_1$ 固定为 1.2，将 $b$ 固定为 0.75。当前项目的 FTS5 列和 BM25 权重是：

| FTS5 列 | 权重 | 作用 |
|---|---:|---|
| `index_id` | 0 | `UNINDEXED`，不参与排序 |
| `chunk_id` | 0 | `UNINDEXED`，不参与排序 |
| `document_id` | 0 | `UNINDEXED`，不参与排序 |
| `title` | 5 | 文档标题命中最重要 |
| `heading_path` | 3 | 章节标题命中次之 |
| `text` | 1 | Chunk 正文基准权重 |

对应实现是 `bm25(chunk_fts, 0.0, 0.0, 0.0, 5.0, 3.0, 1.0)`。可以近似理解为：

$$
f(q_i,D)=5f_{title}+3f_{heading}+f_{text}
$$

例如查询“依赖注入”时，标题就是“依赖项”且章节标题为“什么是依赖注入”的短 Chunk，通常会排在只在长正文中偶然提到该短语的 Chunk 前面。

#### SQLite FTS5 的分数方向

标准 BM25 通常表达为“越大越相关”。SQLite FTS5 为了可以直接使用默认升序排序，在返回值前乘了 $-1$，因此它的原始 `raw_score` 是数值越小越相关，SQL 使用 `ORDER BY raw_score ASC`。

项目返回结果时执行 `score = -raw_score`，只是把展示方向改成“越大看起来越相关”。这个分数不是概率，也不适合跨查询或跨索引版本直接比较。

#### 召回、排序和 rerank 的区别

- 召回：`chunk_fts MATCH ?` 从全部索引行中找出至少命中一个查询 trigram 的候选。
- 一阶段排序：`bm25()` 根据词频、稀有度、长度和字段权重排列这些候选。
- Top-K：`LIMIT ?` 截取前 K 条，例如 `--limit 3`。
- Rerank：应当接收一个更大的候选集，使用独立模型重新打分后再选最终结果；当前没有实现。

代码位置：查询转换在 `retrieval/keyword.py`，FTS5 schema、BM25 权重、最新索引过滤、排序和 `LIMIT` 在 `ingestion/store.py`，CLI 只负责接收 query 与 limit 并输出结果。

### 14. 能召回不等于排序已经正确

真实查询 `message parsing` 的 Top-3 分别是 RFC 摘要、目录页和第 7 页实际正文。三者都包含查询词，因此 BM25 行为合理，但用户通常更希望实际解释正文排在目录之前。

这个结果保留为 BM25 排序坏例。项目现已完成向量与 RRF 的统一评测，但纯 RRF 仍未超过向量基线；当前可以声称三条检索链路可复现并有正式对照，不能笼统声称“检索质量已经优化”。

### 15. 批量流水线必须隔离单文件失败

`DirectoryPipelineService` 递归发现指定扩展名，按相对路径稳定排序，并对每份文件依次执行 ingestion、cleaning、chunking 和 keyword indexing。每份结果保存 `run_id`、各阶段版本 ID、Chunk 数、失败阶段和错误信息。

批量执行不能因为一个损坏 PDF 或待转换 `.doc` 中断其余文档。聚焦测试同时放入有效 Markdown、损坏 PDF 和无关 TXT，验证结果为 1 成功、1 ingestion 失败、1 ignored；另一个测试用非法分块参数确认失败阶段准确记录为 `chunking`。

真实执行结果：125 份 Markdown 全部成功、0 失败。chunker 0.3.0 首次生成 1,200 个最新 Chunk；token 校准后的 chunker 0.4.0 生成 1,222 个 Markdown Chunk。重复执行仍返回相同数量和相同索引身份，搜索不会产生重复命中。默认 CLI 只输出汇总和失败项，`--details` 才展示所有成功文件。

### 16. 小样本通过不代表全量分布健康

单个 CORS 文档的 9 个 Chunk 范围是 73 至 1,007 字符；首次扩展到 125 份后，Markdown 范围变为 2 至 3,585 字符。最短项是只有标题的 Chunk，最长项是明确标记的原子代码块，说明小样本没有覆盖结构分布的尾部。

标题与代码坏例没有采用同一种表面修补：标题必须通过同节或子节前缀检查才能附着，超长代码使用保留原文的换行优先切分并隔离相邻正文。token 风险则在选定模型后用全库分布单独校准，并保留编码前硬防线。chunker 0.4.0 下 125 份 Markdown 共 1,222 个最新 Chunk，范围为 6 至 891；仅标题 Chunk 和超限代码 Chunk 都为 0，6 字符 HTML 闭合标签作为新的清洗坏例保留。

早期真实搜索还发现 `OAuth2` 可以命中，而 `OAuth2 密码` 返回空列表，因为旧版把整个输入构造成 FTS5 精确短语。v0.2.0 改用 trigram `OR` 后已消除整句必须逐字出现才有候选的问题；代价是宽松 OR 会引入更多噪声候选，因此 phrase/all/any 模式和术语降权仍需要单独设计与评测。

### 17. Embedding 生成与向量检索必须分层

`EmbeddingService` 从每份文档的最新 Chunk 版本读取核心文本，通过可注入编码器生成向量，并将模型名、revision、维度、L2 归一化标记、`passage: ` 前缀、最大序列长度、逐 Chunk token 数和截断标记写入 SQLite。向量使用明确的小端 `float32` BLOB，不把 JSON 浮点数组当作长期存储格式。生成和持久化 Embedding 与把它们同步到向量库仍是两个独立、可审计的阶段。

默认模型选择 `intfloat/multilingual-e5-small`，因为当前语料同时包含中文 FastAPI 文档和英文 RFC；适配器固定 CPU、passage 前缀和归一化，并从模型配置记录解析后的 commit `614241f622f53c4eeff9890bdc4f31cfecc418b3`。当前最新版本是 127 个 Embedding 版本、1,362 个 384 维向量，每个 BLOB 为 1,536 字节；L2 范数范围为 0.99999990 至 1.00000012，P95 为 379 tokens、P99 为 451、最大为 488，截断数为 0。物理表中的 254 个版本和 2,675 个向量包含 0.3.0 历史数据，不能当作当前规模。

6 个聚焦 Embedding 测试覆盖 `float32` 往返、版本幂等、向量数量/维度/有限值/范数检查、E5 passage/query 前缀、CPU 参数、revision 解析、token 计数、默认拒绝截断、单文档 CLI 和全库失败隔离；全套共 36 项通过。

上下文重叠暂不写入核心 Chunk 或 BM25 文本，避免重复词项改变排名。后续可为向量索引单独构造带少量邻接行的 `index_text`，或在检索命中后利用已有 `previous_chunk_id` / `next_chunk_id` 扩展上下文。

### 18. Qdrant 快照必须绑定完整模型空间

向量 collection 不能只按模型名命名。当前 `vector_index_id` 同时绑定向量索引器版本、模型名、解析后的 commit、维度、cosine 距离、归一化标记、passage/query 前缀、最大序列长度和 127 个最新 `embedding_id`。同一输入重放得到同一 ID；任一文档重新分块或模型配置变化都会产生新 collection。同步前会拒绝以下状态：最新 Chunk 没有同版本 Embedding、任一向量被截断、不同文档不在同一模型空间、Chunk 与向量序号不一致。

主快照 `vector_f8c4ccfbd78b2742ec7956a7` 对应 collection `enterprise_rag_f8c4ccfbd78b2742ec7956a7`，包含 127 份文档、1,362 个 point，磁盘占用约 6.73 MiB。重复同步后 SQLite 仍只有 1 个 `vector_index_versions` 和 127 个成员，Qdrant point 数保持 1,362。SQLite 只在 Qdrant 全量 upsert 和精确 count 验证成功后记录快照，因此半成品不会成为“最新成功索引”。

查询使用同一模型 commit、`query: ` 前缀、L2 归一化和 cosine Top-K。真实同义问法“后端怎样允许浏览器从其他域名发请求？”的 Top-1 是 `CORSMiddleware` 配置 Chunk，分数约 0.896；Top-5 中 3 条来自 CORS 文档，但 Top-2 是 HTTPS 代理片段。这个结果证明语义召回链路可用，也同时提供了排序坏例；余弦分数不是概率，未经过人工标签时不能据此声称结果正确。

Windows 冒烟还发现：先调用 QdrantLocal `delete_collection()`，再调用 `client.close()` 时，被删除 collection 已从内部注册表移除，`storage.sqlite` 句柄不会被 close 遍历到，临时目录清理触发 `WinError 32`。不可变快照设计避免 delete/recreate；所有命令使用 `closing()` 保证整个 client 释放。真实适配器测试已验证关闭后目录可立即删除。

### 19. AI 种子标签不能冒充人工标注

首批评测集包含 30 个自然语言问题，配置、概念、流程、排障和比较类各 6 条。构建阶段可以自动完成机械工作：定位当前 Chunk、保存精确 `document_id` / `chunk_id`、提取证据、验证证据仍在正文中，并生成带完整上下文和来源链接的 Markdown 审核稿。但“问题是否自然、证据是否真正回答、相关度是 1/2/3、是否遗漏其他正确 Chunk”必须由项目作者独立确认。30 题现已全部完成审核。q009 的原概括证据为 2、具体收益证据为 3；q010 的两段证据共同解释适用场景，但不构成最标准定义，因此均按 2 计；q013、q014、q019 根据人工反馈补充候选后通过；q024 的精确约束为 3，通配符不覆盖凭证通信的原因证据为 2；q026–q030 经审前坏例核对补齐候选后通过。当前 `approved = 30/30`，正式门禁通过。

评测报告保存每题候选、排名、分数、Hit@K、Recall@K、倒数排名和检索延迟；RRF 候选还保存两路 rank/score、RRF score 和向量快照 ID。未全部批准时 `is_provisional=true`；当前三份正式报告均为 `is_provisional=false`。Top-5 结果如下：

| 检索器 | Hit Rate@5 | Recall@5 | MRR | 平均延迟 | P95 延迟 |
|---|---:|---:|---:|---:|---:|
| FTS5 trigram-OR BM25 v0.2.0 | 0.800 | 0.711 | 0.661 | 50.02 ms | 74.72 ms |
| E5 + Qdrant cosine | 0.867 | 0.767 | 0.692 | 21.03 ms | 24.15 ms |
| RRF BM25 + vector，$k=60$，每路 Top-20 | 0.833 | 0.733 | 0.672 | 84.71 ms | 116.90 ms |

RRF 实现 `rrf_bm25_vector_k60_c20_v0.1.0` 只融合排名：同一 `chunk_id` 在每一路最多贡献一次 $1/(60+rank)$，原始 BM25 与 cosine 分数仅用于审计，不参与相加或归一化；最终同分按 `chunk_id` 稳定排序。它不调用额外模型，因此是 rank fusion，不是 rerank。

逐题对照解释了负向结果。RRF 将 BM25 排名 4、向量未命中的 q003 提升到第 1，但最终漏掉 q004、q006、q007、q008 和 q009；其中 q004/q006 原本由向量命中，q007/q008 原本由 BM25 命中。固定 $k=60$ 会让 Top-20 内各名次贡献差距较小，两路都处于中等名次的重叠候选可能排在仅一路高名次的候选之前。当前 30 题上，RRF 优于 BM25 的 Recall/MRR，却低于 E5/Qdrant 三项质量指标；不能声称混合检索带来了质量提升。延迟是本地单次顺序执行两路检索的测量值，不代表并发服务容量。

BM25 初始报告的 30 条查询全部没有候选，不代表 BM25 算法本身失效；根因是 `_fts_query()` 把整个自然问题包装为精确短语，原文不可能逐字包含完整问句。修复后的 `bm25_fts5_trigram_or_v0.2.0` 按索引 tokenizer 对字母数字片段生成去重字符 trigram，并用 `OR` 组合安全的 FTS5 查询。回归测试证明原有中英文短语查询和含引号自然问句都可用；首次修复报告中 30 题均返回 5 个候选，按当时未补全的标签 Top-5 命中 20/30。该历史结果推动了后续漏标核对，不能与当前正式 24/30 命中混用。

BM25 Top-5 命中 24/30，漏掉 q001、q004、q006、q009、q010 和 q016；向量 Top-5 命中 26/30，漏掉 q003、q007、q008 和 q009。q013 的 `UploadFile`、q014 的“响应后运行”与 `add_task()`、q019 的 404/detail、q024 的凭证通配符原因，以及 q030 的主响应/附加响应直接对比 Chunk，原本已被检索器召回，却因标签不完整被计作假阴性。q030 的补标同时消除了 BM25 和向量报告中的假未命中；q026 的 multipart 辅助证据还将 BM25 首个相关排名从 2 提升到 1。30 题全部人工批准后，这些数字可作为公开 FastAPI 语料上的正式基线，但仍不能写成“检索质量已优化”。BM25 查询展开后需要为多个 trigram 计算候选，本次正式平均/P95 延迟为 50.02/74.72 ms，高于空查询时期的 1.91/3.90 ms；这是功能恢复后的真实成本，后续只能在保持 Recall 的前提下优化。

### 20. 上下文扩展必须与锚点排序分开评估

`ContextExpansionService` 的输入是 RRF Top-5 锚点，输出为 `ContextExpansionResult`：原始 `anchor` 保留 rank、两路分数和来源，`expanded_chunks` 保存邻居关系、距离与定位，`context_text` 按源序拼装最终上下文。默认每个锚点向前、向后各检查 1 个当前 Chunk，单锚点字符预算为 2,400；同一邻居只分配给最高排名锚点。扩展不修改 RRF 分数和 rank，因此不能把邻居命中写成检索排序提升。

边界规则不是“只要相邻就拼接”。Markdown/DOCX 只接受完全相同标题路径、标题父子关系或同父兄弟标题；两个无关顶层章节会被拒绝。PDF Chunk 必须仍在同一页，避免引用页码与正文错位。当前 `parent_id` 是 `document_id + heading_path` 的章节身份，不指向一条可读取正文的父 Chunk，因此本阶段是同父级/同章节相邻扩展，不是完整 Parent Document Retrieval。

首版探针只允许完全相同 `parent_id`，没有恢复新的 judgment。逐题检查发现 q007 的相关 Chunk 是 rank-4 锚点的直接子标题邻居，q008 的相关 Chunk 是 rank-5 锚点的同父兄弟标题前邻居；这证明边界比既定“合理父级范围”更窄。v0.2.0 改用标题结构关系后，以相同 Top-20/Top-5、depth=1、2,400 字符预算得到正式结果：

| 指标 | 纯 RRF 锚点 | RRF + 章节相邻扩展 |
|---|---:|---:|
| 锚点 Hit Rate@5 | 0.833 | 0.833 |
| 锚点 Recall@5 | 0.733 | 0.733 |
| 锚点 MRR | 0.672 | 0.672 |
| 扩展证据 Hit Rate@5 | 0.833 | 0.900 |
| 扩展证据 Recall@5 | 0.733 | 0.883 |
| 扩展证据 MRR | 0.672 | 0.696 |

新增命中为 q007 和 q008；q010、q013、q014、q024、q029 的已有命中还补齐了其他 judgment。扩展后仍未命中 q004、q006、q009：q006 的相关文档没有进入 Top-5，邻接扩展无法补救；q004 的同文档相关 Chunk 与最近锚点相隔 13 个 ordinal，q009 的相关 Chunk 相隔 4 至 8 个 ordinal，盲目增加 depth 会显著放大上下文。

成本同样进入正式报告：平均每题新增 5.77 个 Chunk，最终五组锚点上下文平均总长 3,658.9 字符、P95 为 5,643 字符，预算超限锚点为 0；扩展项中 95.4% 没有对应当前 judgment。这里使用 `unjudged_expansion_rate`，而不是“噪声率”，因为 42 条人工 judgment 只标记已确认相关证据，没有证明其他相邻内容全部不相关。下一步 reranker 的目标是保持扩展证据覆盖，同时减少未标注上下文和传给生成模型的 token。

## 可复现检查命令

检查所有文档：

```powershell
.\.venv\Scripts\python.exe -m enterprise_rag_lab list-documents
```

查看 noisy DOCX 原始块：

```powershell
.\.venv\Scripts\python.exe -m enterprise_rag_lab list-blocks `
    doc_6e5efdbd24ca23da7715b812 --limit 30
```

查看 8 条删除审计：

```powershell
.\.venv\Scripts\python.exe -m enterprise_rag_lab inspect-cleaning `
    doc_6e5efdbd24ca23da7715b812
```

查看清洗后保留内容：

```powershell
.\.venv\Scripts\python.exe -m enterprise_rag_lab list-cleaned-blocks `
    doc_6e5efdbd24ca23da7715b812 --limit 30
```

生成并检查 Chunk：

```powershell
.\.venv\Scripts\python.exe -m enterprise_rag_lab chunk-document <document_id>
.\.venv\Scripts\python.exe -m enterprise_rag_lab inspect-chunking <document_id>
.\.venv\Scripts\python.exe -m enterprise_rag_lab list-chunks <document_id> --limit 10
```

建立关键词索引并检索：

```powershell
.\.venv\Scripts\python.exe -m enterprise_rag_lab index-document <document_id>
.\.venv\Scripts\python.exe -m enterprise_rag_lab search "跨域资源共享" --limit 5
.\.venv\Scripts\python.exe -m enterprise_rag_lab search "message parsing" --limit 5
```

安装、生成并检查 Embedding：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,embedding,vector]"
.\.venv\Scripts\python.exe -m enterprise_rag_lab embed-document `
    <document_id> --batch-size 32
.\.venv\Scripts\python.exe -m enterprise_rag_lab embed-all --batch-size 32
.\.venv\Scripts\python.exe -m enterprise_rag_lab inspect-embedding <document_id>
```

同步并检查 Qdrant 快照，再运行向量 Top-K：

```powershell
.\.venv\Scripts\python.exe -m enterprise_rag_lab sync-vector-index --batch-size 128
.\.venv\Scripts\python.exe -m enterprise_rag_lab inspect-vector-index
.\.venv\Scripts\python.exe -m enterprise_rag_lab vector-search `
    "后端怎样允许浏览器从其他域名发请求？" --limit 5
.\.venv\Scripts\python.exe -m enterprise_rag_lab hybrid-search `
    "后端怎样允许浏览器从其他域名发请求？" --candidate-limit 20 --limit 5
.\.venv\Scripts\python.exe -m enterprise_rag_lab hybrid-search `
    "后端怎样允许浏览器从其他域名发请求？" `
    --candidate-limit 20 --limit 5 --expand-context `
    --neighbor-depth 1 --max-context-characters 2400
```

校验种子集、生成 5 条审核材料并运行临时基线：

```powershell
.\.venv\Scripts\python.exe -m enterprise_rag_lab validate-evaluation-set
.\.venv\Scripts\python.exe -m enterprise_rag_lab prepare-evaluation-review `
    --start 1 --limit 5
.\.venv\Scripts\python.exe -m enterprise_rag_lab evaluate-retrieval `
    --retriever bm25 --limit 5
.\.venv\Scripts\python.exe -m enterprise_rag_lab evaluate-retrieval `
    --retriever vector --limit 5
.\.venv\Scripts\python.exe -m enterprise_rag_lab evaluate-retrieval `
    --retriever rrf --candidate-limit 20 --limit 5 --require-approved
.\.venv\Scripts\python.exe -m enterprise_rag_lab evaluate-retrieval `
    --retriever rrf-context --candidate-limit 20 --limit 5 `
    --neighbor-depth 1 --max-context-characters 2400 --require-approved
```

正式评测时增加 `--require-approved`；只要还有一条 `needs_human_review`，命令就必须失败。

批量处理完整 FastAPI Markdown：

```powershell
.\.venv\Scripts\python.exe -m enterprise_rag_lab process-directory `
    data/raw/fastapi `
    --extension md `
    --source-uri-base https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh
```

## 面试复习题

### 为什么不直接覆盖原始文本？

因为覆盖后无法区分解析错误和清洗误删。原始层与清洗层分离后，每个清洗块都能追溯源块，每次规则命中也有 before/after，可支持坏例定位和规则回放。

### Parser Block 和 Chunk 有什么区别？

Parser Block 由源文件结构决定，目标是可定位和无损表达；Chunk 由检索策略决定，目标是控制长度、语义完整性和召回效果。一个 PDF page 可能需要拆成多个 Chunk，多个短段落也可能合并成一个 Chunk。

### 为什么失败任务也要持久化？

只有成功记录会导致失败样本不可统计，也无法判断是格式、依赖还是内容问题。失败 run 保存错误码、消息、路径和耗时，可以支持重试、告警和运营 Agent 分析。

### 为什么清洗规则要版本化？

规则变化会改变索引输入。没有版本就无法重现某次检索使用的文本，也无法做新旧规则的回归对比。版本身份必须进入后续 Chunk 和索引元数据。

### 为什么 PDF 页眉页脚更难？

PDF 常只提供绘制位置和文本片段，没有“页眉”语义。当前方案只检查页首/页尾区域，并要求至少 60% 页面重复后才删除；页码变量先做受约束归一化。这样比无条件删除固定行保守，但复杂版式仍需单独评估。

### 8 个删除块都是重复内容吗？

不是。4 个是同一草稿标签，另外 4 个是下载提示、媒体占位、页眉和页脚。审计必须展示规则构成，不能只展示删除总数。

### 为什么 Chunk 的目标长度不是硬长度？

硬凑长度会切断章节、页码、代码或表格。当前 800 是软目标，900 是经 E5 全库 token 分布校准后的普通文本上限；来源边界优先。过短页尾只在同一页内再平衡，不为了长度跨页拼接。900 不是对未来语料的 token 保证，因此 Embedding 仍会在写入前拒绝超限输入。

### 为什么先实现 BM25 再做向量检索？

BM25 不需要模型服务，结果和分数可解释，适合作为召回基线。只有先固定 Chunk、出处和评测问题，才能客观比较向量召回与 RRF；本项目的正式消融也证明 RRF 并不会自动优于单路向量检索。

### 面试中如何解释当前 Top-3？

`search --limit 3` 将查询拆为去重字符 trigram 并以 `OR` 执行 FTS5 `MATCH`，再由带字段权重的 BM25 一阶段排序并直接 `LIMIT 3`；标题、标题路径、正文权重分别为 5、3、1。`hybrid-search --limit 3` 则先分别取 BM25/向量候选，再按 RRF 分数截取 3 条。两者都不是 rerank，因为没有第二个模型对候选内容重新打分。

### 为什么 RRF 不直接相加 BM25 与 cosine 分数？

两类分数的量纲和分布不同：当前 BM25 对外分数来自 FTS5 排序值，向量分数是 cosine，相加需要额外校准且容易让某一路因数值尺度占优。RRF 只使用各路名次，公式简单、确定、无需训练。代价是它只知道排名，不知道第 1 与第 2 的真实置信差距；本次消融中，两路中等名次的重叠噪声就压过了单路高名次的正确候选，所以 RRF 是可解释基线而不是必然优化。

### 为什么上下文扩展提升了证据 Recall，却没有提升检索 Recall？

检索 Recall 只看 RRF 排名直接返回的锚点 Chunk；上下文扩展发生在排名之后，不会修改锚点。扩展证据 Recall 则把每个锚点及其结构相邻 Chunk 视为一组证据，衡量最终上下文是否覆盖 judgment。两者必须同时报告，否则会把“命中了答案附近”夸大成“检索器把答案排进了 Top-5”。当前扩展证据 Recall 从 0.733 提升到 0.883，但 95.4% 扩展项未标注，说明覆盖收益伴随明显上下文成本。

### 面试中如何用 30 秒解释 BM25？

BM25 是经典的稀疏检索排序算法。它会奖励查询词在文档中的有效出现和稀有词命中，同时通过词频饱和避免“重复堆词”无限加分，并通过长度归一化避免长文档仅因词多而占优。这个项目使用 SQLite FTS5 的 BM25，给标题、标题路径和正文设置 5、3、1 的权重；SQLite 原始分数越小越相关，代码对外取反后显示为越大越相关。它适合作为可解释的关键词基线，但不能替代语义向量召回或第二阶段 rerank。

## 简历素材

以下表述基于当前真实实现和正式评测，可作为阶段性素材；未完成的能力继续单独列出。

### 当前可用表述

> 设计并实现 Markdown、PDF、DOCX 统一文档接入层，保留标题路径、PDF 页码、DOCX 结构元数据及来源哈希；基于稳定 ID 和 SQLite 版本表实现幂等入库，并对成功、失败任务提供可审计运行记录。

> 构建不可变、可回放的文档清洗流水线，将原始解析块、清洗版本和规则命中分层持久化；通过 before/after 审计、规则版本和防误删回归测试控制清洗风险，当前项目测试共 54 项。

> 针对 PDF 缺少页眉页脚语义的问题，实现基于页首/页尾位置、跨页频率阈值与页码归一化的保守清洗策略；在 RFC 9112 的 46 页样本中移除重复模板行，同时保持页面数量、页码连续性和正文验证锚点不变。

> 针对原生 PDF 跨页表格被页级文本抽取拆断的问题，实现基于 bbox、逻辑行、重复横向列起点和页边缘约束的确定性识别与续表合并；在 RFC 9112 中识别 3 张逻辑表，并将 Table 2 自动恢复为跨第 35 至 36 页的 3 列 8 行结构，同时保留逐页来源框。

> 设计版本化、来源可追溯的结构化分块器，按标题路径与 PDF 页边界生成 Chunk，保留父级章节、源块序号和前后邻居；通过同页尾段再平衡将 RFC 样本最小 Chunk 从 13 字符提升到 251 字符，并在全量 Markdown 中消除 19 个仅标题 Chunk 和 7 个超限代码块。

> 基于 SQLite FTS5 trigram 与 BM25 构建中英文关键词检索基线，对 127 份公开或测试文档的 1,362 个最新 Chunk 建立版本化索引，返回标题路径、PDF 页码、来源 URI 和高亮片段，并将排序坏例沉淀为后续混合检索评测输入。

> 实现递归批量知识库流水线，完成 125 份 FastAPI 中文 Markdown 的解析、清洗、结构化分块与关键词索引，生成 1,222 个当前 Chunk；通过单文件失败隔离、精确阶段审计和幂等回放测试避免整批中断及重复召回。

> 设计可注入、版本化的 Embedding 生成层，将模型 commit、维度、归一化配置、token 审计与 Chunk 来源绑定，并以小端 `float32` BLOB 持久化；基于全库分布校准分块并增加默认拒绝截断防线，为 127 份文档的 1,362 个最新 Chunk 生成 384 维无截断向量。

> 实现 Qdrant embedded 不可变向量快照和 E5 余弦 Top-K 检索，将模型 commit、向量配置与 127 个 Embedding 版本绑定；幂等同步 1,362 个 point，并返回标题路径、页码、来源 URI 与快照 ID，支持向量和 RRF 检索结果回放。

> 实现 BM25 Top-20 与 E5/Qdrant Top-20 的确定性 RRF 融合，按 Chunk 去重并保留两路排名、原始分数、融合分数和快照来源；在 30 条人工批准问题、42 条 Chunk judgment 上完成三路 Top-5 消融，RRF Hit Rate/Recall/MRR 实测为 0.833/0.733/0.672，并如实记录未超过向量基线的坏例。

> 实现带标题层级/PDF 页边界、字符预算和跨锚点去重的相邻上下文扩展，分离锚点检索与扩展证据指标；在固定 30 题评测上将证据 Hit Rate/Recall 从 0.833/0.733 提升到 0.900/0.883，同时量化平均 5.77 个扩展 Chunk 和 95.4% 未标注扩展率，为后续 rerank 提供受控基线。

> 排查并修复 Windows 下 SQLite 连接未关闭导致的临时数据库锁定问题，使用事务感知 context manager 统一 commit、rollback 和 close；同时按 code、table、普通文本块类型实施差异化空白规范，避免破坏代码缩进和表格列结构。

### 暂时不能使用的表述

- “处理了企业内部文档”：当前使用公开资料和合成 fixture。
- “支持海量文档”：当前只有 127 份公开或测试文档，没有吞吐、并发和容量测试。
- “完整支持 `.doc`”：当前只支持检测和结构化失败，尚未完成转换。
- “支持任意 PDF 版式”：当前只验证了可提取文本的 RFC 及其原生表格，尚未覆盖扫描件、复杂多栏、并排或旋转表格。
- “实现 Rerank、RAG 问答”：当前完成 BM25、向量 Top-K、RRF 混合检索和章节相邻上下文扩展，尚未实现 rerank 或问答。
- “RRF 提升了检索质量”：当前已有受控对照，但 RRF 的 0.833/0.733/0.672 低于向量基线 0.867/0.767/0.692；只能陈述实现、参数、指标和坏例，不能改写为优化成功。
- “实现完整父文档检索”：当前 `parent_id` 是章节身份，不是一条父文档正文；只能称为同父级/同章节相邻扩展。
- “扩展出的上下文都相关”：当前 95.4% 扩展项没有 judgment，不能把未标注等同相关，也不能等同噪声；需要 reranker 和新增人工标签继续验证。

## 后续复盘模板

以后每完成一个阶段或解决一个真实问题，在本文追加一条：

```markdown
### YYYY-MM-DD：问题标题

- 目标：希望实现什么。
- 症状：实际看到的错误或异常输出。
- 证据：命令、测试、数据库统计或最小复现。
- 根因：最终确认的控制路径和错误假设。
- 方案：做了什么，为什么这样取舍。
- 验证：修改前后结果和回归测试。
- 剩余风险：仍未解决或需要扩展的部分。
- 面试表达：如何在 30 至 60 秒内讲清楚。
- 简历指标：只有真实测量后才填写。
```
