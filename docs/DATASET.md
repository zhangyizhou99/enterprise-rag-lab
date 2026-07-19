# 初始数据集

## 文档领域

FastAPI 官方中文技术文档。

选择原因：文档为公开、结构化的技术资料，包含概念、配置、教程、API 参考和部署等典型企业知识库问题类型；源码以 Markdown 为主，适合作为第一阶段的解析与清洗语料。

## 来源与版本

- 上游仓库：https://github.com/fastapi/fastapi
- 稀疏检出路径：`docs/zh`
- 下载日期：2026-07-18
- 固定 commit：`afe41126f624af30038cc8e17b2aaf60ebd4b838`
- 原始语料目录：`data/raw/fastapi/`
- 上游检出目录：`data/sources/fastapi-upstream/`

上游仓库的许可证与文档版权信息以其仓库中的 `LICENSE` 为准。本项目只将这些公开文档用于本地开发、检索评测和演示，不将语料作为自有内容发布。

## 当前规模

- 格式：Markdown
- 文件数量：125
- 已入库并建立关键词索引：125
- 当前最新 Markdown Chunk：1,222
- 已生成真实 Embedding：127 份文档、1,362 个最新 Chunk，当前截断数 0
- Qdrant embedded 快照：127 份文档、1,362 个 point
- 检索评测种子集：30 条问题、42 条 Chunk judgment，五类各 6 条
- 人工审核状态：`approved = 30`，`needs_human_review = 0`；42 条 Chunk judgment 均已通过当前快照、Chunk 和证据摘录校验
- Embedding 模型：`intfloat/multilingual-e5-small@614241f622f53c4eeff9890bdc4f31cfecc418b3`，384 维
- 语言：中文
- PDF 样本：6
- 默认问答 DOCX 样本：0
- 旧版 Word DOC 样本：1（待转换，默认不索引）
- DOCX 清洗夹具：2（合成内容，默认不索引）

2026-07-19 使用固定 commit 来源 URL 完成 125 份 Markdown 的批量入库、清洗、分块和 FTS5 索引，125 份全部成功、0 失败。chunker 0.3.0 将 19 个仅含标题的 Chunk 安全附着到同节或子节的首个内容 Chunk，并把 7 个超过 1,200 字符的代码块拆成 19 个独立代码 Chunk。随后 chunker 0.4.0 根据 E5 token 分布把默认普通文本上限校准为 900 字符。当前 1,222 是每份 Markdown 文档最新索引的 Chunk 总数，不包含历史版本；字符范围为 6 至 891。唯一低于 14 字符的 Chunk 是 FastAPI 首页中的独立 HTML 闭合标签 `</div>`，不是孤立标题，已记录为后续清洗坏例。

同日首次使用固定 E5 模型 commit 对 1,313 个 Chunk 生成向量时，token 审计发现 6 个 Chunk（0.46%，Markdown 5 个、PDF 1 个）超过 512-token 上限。重建后，主库每份文档最新版本共 1,362 个 L2 归一化 Embedding，127 份全部成功、0 失败；P95 为 379 tokens、P99 为 451、最大值为 488，截断数为 0。历史 0.3.0 Embedding 仍保留用于回放，但不进入当前检索快照。

Qdrant embedded 当前快照 ID 为 `vector_f8c4ccfbd78b2742ec7956a7`，collection 为 `enterprise_rag_f8c4ccfbd78b2742ec7956a7`。它绑定 E5 模型 commit、384 维 cosine 配置和 127 个最新 `embedding_id`，包含 1,362 个 point；重复同步保持同一快照 ID 和 point 数。

### PDF 样本

| 文件 | 来源 | SHA-256 |
|---|---|---|
| `django-5.2.pdf` | https://media.readthedocs.org/pdf/django/5.2.x/django.pdf | `5B57C1ED98F06D632E2E8F54272EF83B28D12C2571679BC9FDC718528F8CEBDF` |
| `postgresql-17-a4.pdf` | https://www.postgresql.org/files/documentation/pdf/17/postgresql-17-A4.pdf | `373847948D91630E85DFD80D54A9929920E666575A4A2A276E081480FD0B4FF1` |
| `requests-latest.pdf` | https://media.readthedocs.org/pdf/requests/latest/requests.pdf | `CA0E1053EA5B88ABC9958AC7182C5344F35F5A429BEA7D3A6EFB24A60832D17E` |
| `rfc-9110.pdf` | https://www.rfc-editor.org/rfc/rfc9110.pdf | `60B30EFA1048900833D1758440247FE8AC85A3134F2327388DCB24E07D814C89` |
| `rfc-9111.pdf` | https://www.rfc-editor.org/rfc/rfc9111.pdf | `2663227A94EC8A81892A02F5697FC15C578571CDEE96407ADB5C60A60236C76F` |
| `rfc-9112.pdf` | https://www.rfc-editor.org/rfc/rfc9112.pdf | `B260BBA790C2DA55A7E0795F356FCD9B70743686C55250F0EF1CC993C4D1ABAC` |

下载日期均为 2026-07-18。Python 官方文档当前不提供预构建 PDF，因此未将其作为 PDF 样本。

### DOCX 清洗夹具

以下合成文档只用于验证 DOCX 解析和清洗规则，位于 `data/fixtures/docx/`，不进入默认问答索引：

- `api-service-deployment-runbook.docx`：包含标题、列表、表格、代码片段和页眉页脚的正常运维手册。
- `cors-incident-postmortem-noisy.docx`：包含重复页眉页脚、空白段落、图片占位文字等可复现噪声的故障复盘文档。

### 旧版 Word DOC 待转换语料

`data/raw/docx/儿童发展心理学.doc` 是一篇新增的中文儿童发展心理学文章，用作真实旧版 Word 文档兼容性样本。该文件会在完成来源信息补录和格式转换后进入问答语料；在此之前，默认索引应跳过它。

| 字段 | 当前值 |
|---|---|
| 原始格式 | `doc`（旧版 Microsoft Word 二进制格式） |
| 文件大小 | 159,232 bytes |
| SHA-256 | `EBCF70BC0D61398900071D9DCC22218ACE48C2B4C44A833F88B81B83B2C20CA1` |
| 内容领域 | 儿童发展心理学 |
| 来源 URL / 作者 / 许可 | 待补录；未补录前仅作本地兼容性测试，不对外发布 |
| 索引状态 | `pending_conversion` |

`python-docx` 不能直接读取 `.doc`。项目统一使用 LibreOffice 的无界面命令行工具 `soffice` 转换，然后复用 DOCX 解析器：

```powershell
winget install --id TheDocumentFoundation.LibreOffice --exact --accept-package-agreements --accept-source-agreements

New-Item -ItemType Directory -Force data\converted | Out-Null
& "C:\Program Files\LibreOffice\program\soffice.exe" `
	--headless `
	--convert-to docx `
	--outdir data\converted `
	"data\raw\docx\儿童发展心理学.doc"
```

转换时必须保留原始文件名、原始 SHA-256、转换时间、转换器版本和转换后文件的 SHA-256。检索结果仍标记 `source_format = "doc"`，并引用原始 `.doc` 文件；转换后的 `.docx` 只是解析中间产物，不应被当成新的独立资料。

## 首批评测问题类型

- 配置：如 CORS、依赖注入和安全认证配置。
- 概念：如路径参数、请求体、异步并发模型。
- 流程：如开发、测试与部署步骤。
- 排障：如常见配置和运行错误。

种子集位于 `data/evaluation/fastapi_retrieval_v1.json`，绑定当前向量快照 `vector_f8c4ccfbd78b2742ec7956a7`。每个 judgment 都已通过“最新 Chunk 存在且证据摘录位于正文中”的结构校验；30 条问题、42 条 Chunk judgment 已由项目作者完成独立判断，当前 `approved = 30/30`、`needs_human_review = 0`。正式评测仍必须使用 `--require-approved`，防止后续数据集修改后把待审核结果误记为正式指标。

## 已知限制

- 默认问答语料以 FastAPI 官方中文文档为主，PDF 补充了 Django、PostgreSQL、Requests 和 HTTP 标准等公开技术资料；尚不能代表跨部门、跨系统的真实企业文档分布。
- PDF 主要为英文，核心 FastAPI Markdown 为中文；当前没有进入默认问答索引的 DOCX 语料。后续应在评测集中分别标注语言与问题类型。
