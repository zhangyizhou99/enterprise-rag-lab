# Enterprise RAG Lab

一个独立的企业文档知识库 RAG 项目，用于完整实践文档接入、数据清洗、混合检索、重排、带引用问答、评测与用户反馈闭环。

完整的分阶段实施计划见 [开发计划](docs/DEVELOPMENT_PLAN.md)，实际遇到的技术难点、设计取舍、验证证据和简历素材持续记录在 [工程复盘](docs/ENGINEERING_REVIEW.md)。

## 产品目标

- 接入 Markdown、DOCX 与 PDF 文档，保留原始文件与可检索文本。
- 对来源杂乱的文档执行可回放、可回归测试的数据清洗。
- 结合关键词和向量检索，使用重排模型提高答案片段的召回质量。
- 用父子文档与相邻片段扩展，避免只命中摘要而遗漏答案正文。
- 回答必须展示引用和原文入口；证据不足时明确拒答。
- 通过人工标注评测集和点赞/点踩反馈，持续量化并优化效果。

## 第一阶段范围

1. 文档解析与元数据模型。
2. 可测试的清洗流水线。
3. 文档级、片段级父子关系与索引接口。
4. 混合检索、RRF 融合、可替换的 rerank 接口。
5. 带引用的问答 API 与评测基线。

## 设计原则

- 先跑通端到端闭环，再替换单点组件为生产实现。
- 默认使用 Docker Compose 组织本地依赖；后续可升级到服务化向量库与对象存储。
- 以评测数据决定检索策略，不以主观观感代替指标。
- 真实记录规模、成本、延迟和评测结果，不伪造企业数据。

## 规划架构

```text
上传文档 -> 解析/清洗 -> 原文对象存储 + 元数据数据库
                         -> 文档/片段索引 -> 混合召回 -> Rerank
用户提问 -> Query Rewrite -> 证据拼装 -> LLM 回答 + 引用
                                             -> 点赞/点踩 -> 评测与迭代
```

`sentinel` 是独立的代码可观测性 Agent；本项目不复用其业务模块。

## 当前可运行能力

统一解析器已支持 Markdown、PDF 和 DOCX，并将文档、解析版本、来源定位块和运行状态写入 SQLite。PDF parser 0.3.0 会对原生文本 PDF 识别表格区域、恢复行列，并基于相邻页、重复表头、列起点和页边缘位置合并跨页续表。目录流水线可以递归执行入库、清洗、分块和关键词索引，单文件失败不会中止整批。清洗结果可生成带标题、页码、源块和前后邻居的版本化 Chunk，并使用 SQLite FTS5 trigram 索引完成中英文 BM25 关键词检索。项目已实现可注入的 Embedding 生成服务、版本化 `float32` 存储、Qdrant embedded 不可变快照、余弦 Top-K、BM25/向量候选的确定性 RRF 融合，以及带字符预算的同章节相邻上下文扩展；真实模型依赖与模型文件需要单独安装下载。旧版 `.doc` 会返回可操作的 LibreOffice 转换错误，并将失败原因写入运行记录。

首次运行时，在项目根目录创建独立虚拟环境并以 editable 模式安装项目：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

需要运行本地 Embedding 模型和 Qdrant embedded 时，再安装可选依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,embedding,vector]"
```

此后可以激活环境再执行命令：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

```powershell
python -m enterprise_rag_lab ingest `
    data/raw/fastapi/docs/tutorial/cors.md `
    --source-uri https://github.com/fastapi/fastapi/blob/main/docs/zh/docs/tutorial/cors.md

python -m enterprise_rag_lab process-directory `
    data/raw/fastapi `
    --extension md `
    --source-uri-base https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh

python -m enterprise_rag_lab inspect-run <run_id>

python -m enterprise_rag_lab list-documents
python -m enterprise_rag_lab inspect-document <document_id>
python -m enterprise_rag_lab list-blocks <document_id> --limit 10

python -m enterprise_rag_lab clean-document <document_id>
python -m enterprise_rag_lab inspect-cleaning <document_id>
python -m enterprise_rag_lab list-cleaned-blocks <document_id> --limit 10

python -m enterprise_rag_lab chunk-document <document_id>
python -m enterprise_rag_lab inspect-chunking <document_id>
python -m enterprise_rag_lab list-chunks <document_id> --limit 10

python -m enterprise_rag_lab index-document <document_id>
python -m enterprise_rag_lab inspect-index <document_id>
python -m enterprise_rag_lab search "跨域资源共享" --limit 5

python -m enterprise_rag_lab embed-document <document_id> --batch-size 32
python -m enterprise_rag_lab embed-all --batch-size 32
python -m enterprise_rag_lab inspect-embedding <document_id>

python -m enterprise_rag_lab sync-vector-index --batch-size 128
python -m enterprise_rag_lab inspect-vector-index
python -m enterprise_rag_lab vector-search "如何配置跨域请求？" --limit 5
python -m enterprise_rag_lab hybrid-search "如何配置跨域请求？" --candidate-limit 20 --limit 5
python -m enterprise_rag_lab hybrid-search "如何配置跨域请求？" `
    --candidate-limit 20 --limit 5 --expand-context `
    --neighbor-depth 1 --max-context-characters 2400

python -m enterprise_rag_lab validate-evaluation-set
python -m enterprise_rag_lab prepare-evaluation-review --start 1 --limit 5
python -m enterprise_rag_lab evaluate-retrieval --retriever bm25 --limit 5
python -m enterprise_rag_lab evaluate-retrieval --retriever vector --limit 5
python -m enterprise_rag_lab evaluate-retrieval --retriever rrf --candidate-limit 20 --limit 5 --require-approved
python -m enterprise_rag_lab evaluate-retrieval --retriever rrf-context `
    --candidate-limit 20 --neighbor-depth 1 `
    --max-context-characters 2400 --limit 5 --require-approved
```

不激活环境时，也可以将上述命令中的 `python` 替换为 `.\.venv\Scripts\python.exe`。`PYTHONPATH=src` 仅适合临时开发，不是常规运行所必需的配置。

默认数据库位于 `data/state/ingestion.sqlite3`，Qdrant embedded 数据位于 `data/state/qdrant`。可在命令前使用 `--database <path>` 覆盖 SQLite 路径，向量命令使用 `--qdrant-path <path>` 覆盖 Qdrant 路径。

`process-directory` 默认递归处理支持格式，可重复使用 `--extension` 限定格式。默认 JSON 只返回汇总和失败文件；增加 `--details` 才展开全部成功结果。当前 125 份 FastAPI Markdown 已全部处理成功，使用 chunker 0.4.0 生成 1,222 个最新 Chunk。

## 清洗结果校验

清洗不会覆盖 `parsed_blocks`。每个结果都绑定源解析版本、清洗器版本和规则集版本，因此相同输入可以确定性重放：

- `clean-document` 执行清洗，显示输入/输出块数、字符数变化和规则命中计数。
- `inspect-cleaning` 显示每次删除或替换的源块序号、规则、修改前文本和修改后文本。
- `list-blocks` 查看解析器原始块，`list-cleaned-blocks` 查看清洗块；两者通过 `source_ordinal` 对照。

当前规则会规范普通文本空白、移除 DOCX 页眉页脚和明确的草稿/下载/媒体占位提示，并对完全相同的正文段落去重。代码缩进、表格制表符、标题路径和 PDF 页码会保留。

### PDF 长表识别范围

当前实现面向有可用文本层的原生 PDF。`pdfplumber_rows_v0.1.0` 先识别表格边界和逻辑行，再从重复的横向起点恢复列；若前一页最后一张表位于页底、后一页第一张表位于页顶，并且表头与标准化列起点一致，则合并为一个逻辑表。每张表保存来源页、逐页 bbox、行列数、表头、识别器及库版本。RFC 9112 回归样本共识别 3 张逻辑表、4 个页面表片段，其中 Table 2 被自动恢复为跨第 35 至 36 页的 3 列 8 行表格，且未混入第 36 页参考文献。

当前不支持扫描表格 OCR、复杂并排表格、旋转表格或视觉模型兜底。识别结果已进入 parser/cleaner，但超长表格按行分块、重复表头和跨页范围向最终 Chunk 的完整传播尚未实现；这些是后续切片，不应将当前能力描述为任意 PDF 表格支持。

## 分块、关键词、向量、RRF 与上下文扩展

默认分块软目标为 800 字符，普通文本上限为 900 字符。该上限来自当前全库 E5 token 分布校准：相比 1,200 字符版本，最新 Chunk 从 1,313 增至 1,362，最大 token 数从 572 降至 488。分块不会跨越标题路径或 PDF 页码；表格目前保持原子性，超长代码优先在当前窗口后半段的换行处拆分，没有合适换行时按字符上限兜底。普通长文本只在提取行、句子或单词边界拆分。每个 Chunk 保存清洗版本、父级章节、源块序号和前后邻居。900 字符是对当前语料的经验校准，不是对所有未来语料的 token 数学保证；Embedding 默认拒绝保存超过模型上限的输入，只有显式传入 `--allow-truncation` 才允许截断。PDF parser 已能标记跨页表格，但当前 Chunker 尚未按行拆分长表或把表格的 `page_end` 从 metadata 提升到 Chunk 页范围。

关键词索引使用 SQLite FTS5 `trigram` tokenizer，兼容当前中英文混合样本，并使用 `bm25()` 排序。查询策略 `bm25_fts5_trigram_or_v0.2.0` 将可检索文字片段拆成去重字符 trigram，再用 `OR` 组合为安全的 FTS5 查询；这避免了自然问句必须逐字出现在原文中才有候选的问题。它既是可解释的独立基线，也是 RRF 的一路输入；当前仍不包含停用模式降权、实体/术语提取或同义词扩展。

Embedding 默认配置为 CPU 上的 `intfloat/multilingual-e5-small`，文档输入使用 `passage: ` 前缀，查询使用 `query: ` 前缀，并执行 L2 归一化。每个版本记录模型名、解析后的 revision、维度、最大序列长度、token 数和截断数量；向量以小端 `float32` BLOB 保存到 SQLite。当前主数据库已为 127 份文档的 1,362 个最新 Chunk 生成 384 维真实向量，模型 commit 为 `614241f622f53c4eeff9890bdc4f31cfecc418b3`，最新版本截断数为 0。

`sync-vector-index` 只接受与最新 Chunk 完全匹配、未截断且属于同一模型空间的 Embedding。快照 ID 绑定索引器版本、模型 commit、向量配置和全部成员 `embedding_id`；同一快照可幂等重放，任一 Chunk 或模型变化都会生成新 collection。当前主快照为 `vector_f8c4ccfbd78b2742ec7956a7`，包含 127 份文档、1,362 个 Qdrant point。`vector-search` 返回余弦相似度、原文、标题路径、页码和来源 URI；该分数不是概率。

`hybrid-search` 分别获取 BM25 Top-20 和向量 Top-20，按 `chunk_id` 去重后使用固定 $k=60$ 的 `1 / (k + rank)` 求和，最后返回 Top-5。`rrf_bm25_vector_k60_c20_v0.1.0` 保留两路原始 rank/score、RRF score 和向量快照 ID，但原始 BM25 与 cosine 分数不参与相加或归一化。RRF 是无需额外模型的排名融合，不是 rerank。

增加 `--expand-context` 后，`context_section_d1_b2400_v0.2.0` 为每个锚点检查前后各 1 个当前 Chunk，只接受同一标题路径、标题父子关系或同父兄弟标题，PDF 不跨页；单个锚点上下文最多 2,400 字符。锚点排名和 RRF 分数不变，共享邻居只归入最高排名锚点，输出明确区分 `anchor`、`expanded_chunks` 和 `context_text`。当前 `parent_id` 是章节身份而不是可读取正文的父 Chunk，因此已实现的是“同父级/同章节相邻扩展”，不能称为完整父文档检索。rerank、高级查询预处理和生成问答仍未实现。

## 检索评测与人工审核

`data/evaluation/fastapi_retrieval_v1.json` 包含 30 条问题，配置、概念、流程、排障和比较类各 6 条，当前共有 42 个 Chunk judgment。每条 judgment 都绑定当前 `document_id`、`chunk_id` 和原文摘录；30 条问题均已由项目作者人工审核，当前 `approved = 30/30`、`needs_human_review = 0`。q009 根据首轮反馈保留相关度 2 的概括证据，并补充相关度 3 的具体收益证据；q010 的两段证据共同解释适用场景，但都不是标准定义，因此均按相关度 2 计。q013、q014、q019 按人工反馈补齐证据后通过，q024 以相关度 3 的配置约束和相关度 2 的通配符原因共同支撑结论，q026–q030 在审前坏例核对中补齐遗漏候选后通过。`prepare-evaluation-review` 会生成包含完整 Chunk、标题路径和来源链接的 Markdown 审核批次；本阶段评估的是“问题 → Chunk”的检索相关性，不包含生成答案。

`evaluate-retrieval` 将每题候选、排名、分数和延迟保存到 `data/evaluation/reports/`。RRF 报告还保存两路 rank/score 与向量快照 ID，上下文报告继续保存扩展关系、距离和最终上下文。未全部批准时报告强制标记 `is_provisional=true`；正式运行使用 `--require-approved`。当前正式 Top-5 结果为：BM25 Hit Rate 0.800、Recall 0.711、MRR 0.661；E5/Qdrant 为 0.867、0.767、0.692；RRF 为 0.833、0.733、0.672，三份排名报告均为 `is_provisional=false`。BM25 最初因整句精确短语查询导致 30 题全部无候选；改为版本化 trigram `OR` 查询后，30 题均有候选。补充 q013、q014、q019、q024、q026、q027、q029、q030 的有效 judgment 后，原本已召回的正确 Chunk 不再被计作假阴性。

本次固定参数消融中，RRF 恢复了向量未命中的 q003，却因偏好两路重叠候选而漏掉 q004、q006、q007、q008 和 q009，整体没有超过向量基线。加入 depth=1、每锚点 2,400 字符的章节相邻扩展后，锚点指标仍为 0.833/0.733/0.672；单独计算的扩展证据 Hit Rate/Recall/MRR 为 0.900/0.883/0.696，恢复 q007、q008，并补全 q010、q013、q014、q024、q029 的部分标注证据。平均每题新增 5.77 个 Chunk、上下文总长 3,658.9 字符，P95 为 5,643 字符；95.4% 扩展项未出现在当前 judgment 中。`unjudged` 既不能直接算相关，也不能直接叫噪声，说明下一步应由 reranker 压缩候选并扩大人工评审，而不是直接把所有扩展内容交给生成模型。
