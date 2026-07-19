# fastapi_retrieval_v1 人工审核 11-15

- 语料快照：`vector_f8c4ccfbd78b2742ec7956a7`
- 数据集哈希：`1590889014839d3eba2acd8b816627b5e928260909d885f932664397dcfbc3bd`
- 本批题数：5
- 说明：以下相关度是种子建议，不是人工结论。逐题确认后才能将 `review_status` 改为 `approved`。
- 审核对象：本阶段只评估“问题 → Chunk”的检索相关性，尚未生成答案。请判断完整 Chunk 是否含有足以支撑回答的事实，不需要撰写标准答案、查找 ID 或自行搜索语料库。

相关度口径：`3` 直接完整回答；`2` 部分回答或重要辅助证据；`1` 弱相关；不相关则删除该 judgment。

## q011 · concept

**问题**：OAuth2 作用域在 OpenAPI 中表示什么？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：OAuth2 作用域
- 标题路径：OAuth2 作用域 > OAuth2 作用域与 OpenAPI
- `document_id`：`doc_607d460b46995276b17d9ca8`
- `chunk_id`：`chunk_340b4566dead6f8cf54a0ff3`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/advanced/security/oauth2-scopes.md

**证据摘录**

```text
OAuth2 作用域与 OpenAPI
```

**当前完整 Chunk**

```text
OAuth2 作用域与 OpenAPI

OAuth2 规范将“作用域”定义为由空格分隔的字符串列表。

这些字符串的内容可以是任意格式，但不应包含空格。

这些作用域表示“权限”。

在 OpenAPI（例如 API 文档）中，你可以定义“安全方案”（security schemes）。

当这些安全方案使用 OAuth2 时，你还可以声明并使用作用域。

每个“作用域”只是一个（不带空格的）字符串。

它们通常用于声明特定的安全权限，例如：

* 常见示例：`users:read` 或 `users:write`
* Facebook / Instagram 使用 `instagram_basic`
* Google 使用 `https://www.googleapis.com/auth/drive`

/// note | 注意

在 OAuth2 中，“作用域”只是一个声明所需特定权限的字符串。

是否包含像 `:` 这样的字符，或者是不是一个 URL，并不重要。

这些细节取决于具体实现。

对 OAuth2 而言，它们都只是字符串。
```

---

## q012 · concept

**问题**：FastAPI lifespan 中 yield 前后的代码分别在什么时候运行？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：生命周期事件
- 标题路径：生命周期事件 > Lifespan
- `document_id`：`doc_a89bf7973136039afbc4a93b`
- `chunk_id`：`chunk_b5b6c3d7b623bc3b8cf0f34e`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/advanced/events.md

**证据摘录**

```text
在 `yield` 之前
```

**当前完整 Chunk**

```text
Lifespan

你可以使用 `FastAPI` 应用的 `lifespan` 参数和一个“上下文管理器”（稍后我将为你展示）来定义**启动**和**关闭**的逻辑。

让我们从一个例子开始，然后详细介绍。

我们使用 `yield` 创建了一个异步函数 `lifespan()` 像这样：

{* ../../docs_src/events/tutorial003_py310.py hl[16,19] *}

在这里，我们在 `yield` 之前将（虚拟的）模型函数放入机器学习模型的字典中，以此模拟加载模型的耗时**启动**操作。这段代码将在应用程序**开始处理请求之前**执行，即**启动**期间。

然后，在 `yield` 之后，我们卸载模型。这段代码将会在应用程序**完成处理请求后**执行，即在**关闭**之前。这可以释放诸如内存或 GPU 之类的资源。

/// tip | 提示

**关闭**事件会在你**停止**应用时发生。

可能你需要启动一个新版本，或者你只是厌倦了运行它。 🤷

///
```

---

## q013 · procedure

**问题**：接收上传文件时，怎样避免把整个文件一次性放进内存？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`2`
- 文档：请求文件
- 标题路径：请求文件 > 定义 `File` 参数
- `document_id`：`doc_dd056858ebb5465a1555d664`
- `chunk_id`：`chunk_4cead67dfb5d44051c0d9746`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/request-files.md

**证据摘录**

```text
整个内容会存储在内存中
```

**当前完整 Chunk**

```text
定义 `File` 参数

像为 `Body` 或 `Form` 一样创建文件参数：

{* ../../docs_src/request_files/tutorial001_an_py310.py hl[9] *}

`File` 是直接继承自 `Form` 的类。

但要注意，从 `fastapi` 导入的 `Query`、`Path`、`File` 等项，实际上是返回特定类的函数。

/// tip | 提示

声明文件体必须使用 `File`，否则，这些参数会被当作查询参数或请求体（JSON）参数。

文件将作为「表单数据」上传。

如果把*路径操作函数*参数的类型声明为 `bytes`，**FastAPI** 会为你读取文件，并以 `bytes` 的形式接收其内容。

请注意，这意味着整个内容会存储在内存中，适用于小型文件。

不过，在很多情况下，使用 `UploadFile` 会更有优势。
```

### 候选证据 2

- 建议相关度：`3`
- 文档：请求文件
- 标题路径：请求文件 > 含 `UploadFile` 的文件参数
- `document_id`：`doc_dd056858ebb5465a1555d664`
- `chunk_id`：`chunk_1c100f3b23c678ee64563b5e`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/request-files.md

**证据摘录**

```text
超过该上限后会写入磁盘
```

**当前完整 Chunk**

```text
含 `UploadFile` 的文件参数

将文件参数的类型声明为 `UploadFile`：

{* ../../docs_src/request_files/tutorial001_an_py310.py hl[14] *}

与 `bytes` 相比，使用 `UploadFile` 有多项优势：

* 无需在参数的默认值中使用 `File()`。
* 它使用“spooled”文件：
* 文件会先存储在内存中，直到达到最大上限，超过该上限后会写入磁盘。
* 因此，非常适合处理图像、视频、大型二进制等大文件，而不会占用所有内存。
* 你可以获取上传文件的元数据。
* 它提供 [file-like](https://docs.python.org/3/glossary.html#term-file-like-object) 的 `async` 接口。
* 它暴露了一个实际的 Python [`SpooledTemporaryFile`](https://docs.python.org/3/library/tempfile.html#tempfile.SpooledTemporaryFile) 对象，你可以直接传给期望「file-like」对象的其他库。
```

**备注**：人工复核认为原 Chunk 只说明 bytes 的内存问题并提示 UploadFile，已降为相关度 2；补充 UploadFile 使用 spooled 文件、超过阈值写入磁盘的完整候选证据。

---

## q014 · procedure

**问题**：如何在响应返回后执行发送邮件之类的小型后台任务？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`2`
- 文档：后台任务
- 标题路径：后台任务 > 使用 `BackgroundTasks`
- `document_id`：`doc_f4160099413bd4b00b7caf17`
- `chunk_id`：`chunk_2c6a42ec0026a2bacdf7a622`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/background-tasks.md

**证据摘录**

```text
BackgroundTasks
```

**当前完整 Chunk**

```text
使用 `BackgroundTasks`

首先导入 `BackgroundTasks` 并在 *路径操作函数* 中使用类型声明 `BackgroundTasks` 定义一个参数：

{* ../../docs_src/background_tasks/tutorial001_py310.py hl[1,13] *}

**FastAPI** 会创建一个 `BackgroundTasks` 类型的对象并作为该参数传入。
```

### 候选证据 2

- 建议相关度：`2`
- 文档：后台任务
- 标题路径：后台任务
- `document_id`：`doc_f4160099413bd4b00b7caf17`
- `chunk_id`：`chunk_160bb5c1c23038cf07b2e47b`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/background-tasks.md

**证据摘录**

```text
在返回响应后运行的后台任务
```

**当前完整 Chunk**

```text
后台任务

你可以定义在返回响应后运行的后台任务。

这对需要在请求之后执行的操作很有用，但客户端不必在接收响应之前等待操作完成。

包括这些例子：

* 执行操作后发送的电子邮件通知：
* 由于连接到电子邮件服务器并发送电子邮件往往很“慢”（几秒钟），您可以立即返回响应并在后台发送电子邮件通知。
* 处理数据：
* 例如，假设您收到的文件必须经过一个缓慢的过程，您可以返回一个"Accepted"(HTTP 202)响应并在后台处理它。
```

### 候选证据 3

- 建议相关度：`2`
- 文档：后台任务
- 标题路径：后台任务 > 添加后台任务
- `document_id`：`doc_f4160099413bd4b00b7caf17`
- `chunk_id`：`chunk_d8d8f82e6341c7eec8ab78b8`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/background-tasks.md

**证据摘录**

```text
用 `.add_task()` 方法将任务函数传到 *后台任务* 对象中
```

**当前完整 Chunk**

```text
添加后台任务

在你的 *路径操作函数* 里，用 `.add_task()` 方法将任务函数传到 *后台任务* 对象中：

{* ../../docs_src/background_tasks/tutorial001_py310.py hl[14] *}

`.add_task()` 接收以下参数：

* 在后台运行的任务函数(`write_notification`)。
* 应按顺序传递给任务函数的任意参数序列(`email`)。
* 应传递给任务函数的任意关键字参数(`message="some notification"`)。
```

**备注**：人工复核认为原 Chunk 只说明注入 BackgroundTasks。官方说明按标题分为互补 Chunk：响应后运行、注入对象和 add_task() 注册任务；没有单个 Chunk 独立完整回答，因此三段均按相关度 2 等待复核。

---

## q015 · procedure

**问题**：如何使用 pytest 和 TestClient 测试 FastAPI 接口？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：测试
- 标题路径：测试 > 使用 `TestClient`
- `document_id`：`doc_b83759371bdb806a5fd2c6e2`
- `chunk_id`：`chunk_c6750402a44b88084a812fc5`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/testing.md

**证据摘录**

```text
通过传入你的**FastAPI**应用创建一个 `TestClient`
```

**当前完整 Chunk**

```text
使用 `TestClient`

/// note | 注意

要使用 `TestClient`，先要安装 [`httpx`](https://www.python-httpx.org)。

确保你创建并激活一个[虚拟环境](../virtual-environments.md)，然后再安装，例如：

$ pip install httpx

///

导入 `TestClient`。

通过传入你的**FastAPI**应用创建一个 `TestClient` 。

创建名字以 `test_` 开头的函数（这是标准的 `pytest` 约定）。

像使用 `httpx` 那样使用 `TestClient` 对象。

为你需要检查的地方用标准的Python表达式写个简单的 `assert` 语句（重申，标准的`pytest`）。

{* ../../docs_src/app_testing/tutorial001_py310.py hl[2,12,15:18] *}

/// tip | 提示

注意测试函数是普通的 `def`，不是 `async def`。

还有client的调用也是普通的调用，不是用 `await`。

这让你可以直接使用 `pytest` 而不会遇到麻烦。

/// note | 技术细节

你也可以用 `from starlette.testclient import TestClient`。

**FastAPI** 提供了和 `starlette.testclient` 一样的 `fastapi.testclient`，只是为了方便开发者。但它直接来自Starlette。

除了发送请求之外，如果你还想测试时在FastAPI应用中调用 `async` 函数（例如异步数据库函数）， 可以在高级教程中看下[异步测试](../advanced/async-tests.md)。
```

---
