# fastapi_retrieval_v1 人工审核 26-30

- 语料快照：`vector_f8c4ccfbd78b2742ec7956a7`
- 数据集哈希：`b92d7fbb8670818d75050b7d1a4c94acfdc86e654a050b6b2f5ae171d0a7b9f6`
- 本批题数：5
- 说明：以下相关度是种子建议，不是人工结论。逐题确认后才能将 `review_status` 改为 `approved`。
- 审核对象：本阶段只评估“问题 → Chunk”的检索相关性，尚未生成答案。请判断完整 Chunk 是否含有足以支撑回答的事实，不需要撰写标准答案、查找 ID 或自行搜索语料库。

相关度口径：`3` 直接完整回答；`2` 部分回答或重要辅助证据；`1` 弱相关；不相关则删除该 judgment。

## q026 · comparison

**问题**：为什么同一个路径操作不能同时接收 Form 字段和 JSON Body 字段？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：表单数据
- 标题路径：表单数据 > 关于 "表单字段"
- `document_id`：`doc_0e7fa92cd4cc5d1e1256d42d`
- `chunk_id`：`chunk_2f068becc3f463bd401382f5`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/request-forms.md

**证据摘录**

```text
不能同时再声明要接收为 JSON 的 `Body` 字段
```

**当前完整 Chunk**

```text
关于 "表单字段"

HTML 表单（`<form></form>`）向服务器发送数据时通常会对数据使用一种“特殊”的编码方式，这与 JSON 不同。

**FastAPI** 会确保从正确的位置读取这些数据，而不是从 JSON 中读取。

/// note | 技术细节

表单数据通常使用“媒体类型” `application/x-www-form-urlencoded` 进行编码。

但当表单包含文件时，会编码为 `multipart/form-data`。你将在下一章阅读如何处理文件。

如果你想了解更多关于这些编码和表单字段的信息，请参阅 [<abbr title="Mozilla Developer Network - Mozilla 开发者网络">MDN</abbr> Web 文档的 `POST`](https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods/POST)。

/// warning | 警告

你可以在一个*路径操作*中声明多个 `Form` 参数，但不能同时再声明要接收为 JSON 的 `Body` 字段，因为此时请求体会使用 `application/x-www-form-urlencoded` 而不是 `application/json` 进行编码。

这不是 **FastAPI** 的限制，而是 HTTP 协议的一部分。
```

### 候选证据 2

- 建议相关度：`2`
- 文档：请求表单与文件
- 标题路径：请求表单与文件 > 定义 `File` 与 `Form` 参数
- `document_id`：`doc_fd14dd0474d471ab9a82a331`
- `chunk_id`：`chunk_9beeec73001bd7c1b0d5a64f`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/request-forms-and-files.md

**证据摘录**

```text
不能同时声明要接收 JSON 的 `Body` 字段
```

**当前完整 Chunk**

```text
定义 `File` 与 `Form` 参数

创建文件和表单参数的方式与 `Body` 和 `Query` 一样：

{* ../../docs_src/request_forms_and_files/tutorial001_an_py310.py hl[10:12] *}

文件和表单字段作为表单数据上传与接收。

并且你可以将部分文件声明为 `bytes`，将部分文件声明为 `UploadFile`。

/// warning | 警告

可在一个*路径操作*中声明多个 `File` 与 `Form` 参数，但不能同时声明要接收 JSON 的 `Body` 字段。因为此时请求体的编码为 `multipart/form-data`，不是 `application/json`。

这不是 **FastAPI** 的问题，而是 HTTP 协议的规定。
```

**备注**：原 Chunk 直接解释纯 Form 请求使用 application/x-www-form-urlencoded；补充 File 与 Form 并用时请求体改为 multipart/form-data 的同类限制。

---

## q027 · comparison

**问题**：在 FastAPI 中兼容 Flask 或 Django 这类 WSGI 应用时需要什么包装层？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：包含 WSGI - Flask，Django，其它
- 标题路径：包含 WSGI - Flask，Django，其它
- `document_id`：`doc_9ded5f89cfb34b9f01100adb`
- `chunk_id`：`chunk_702ee4fcb7f1d016a81152f6`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/advanced/wsgi.md

**证据摘录**

```text
`WSGIMiddleware` 来包装你的 WSGI 应用
```

**当前完整 Chunk**

```text
包含 WSGI - Flask，Django，其它

您可以挂载 WSGI 应用，正如您在 [子应用 - 挂载](sub-applications.md)、[在代理之后](behind-a-proxy.md) 中所看到的那样。

为此, 您可以使用 `WSGIMiddleware` 来包装你的 WSGI 应用，如：Flask，Django，等等。
```

### 候选证据 2

- 建议相关度：`3`
- 文档：包含 WSGI - Flask，Django，其它
- 标题路径：包含 WSGI - Flask，Django，其它 > 使用 `WSGIMiddleware`
- `document_id`：`doc_9ded5f89cfb34b9f01100adb`
- `chunk_id`：`chunk_c35facbf4c14d136891ea896`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/advanced/wsgi.md

**证据摘录**

```text
从 `a2wsgi` 导入 `WSGIMiddleware`
```

**当前完整 Chunk**

```text
使用 `WSGIMiddleware`

/// note | 注意

需要安装 `a2wsgi`，例如使用 `pip install a2wsgi`。

///

您需要从 `a2wsgi` 导入 `WSGIMiddleware`。

然后使用该中间件包装 WSGI 应用（例如 Flask）。

之后将其挂载到某一个路径下。

{* ../../docs_src/wsgi/tutorial001_py310.py hl[1,3,23] *}

之前推荐使用 `fastapi.middleware.wsgi` 中的 `WSGIMiddleware`，但它现在已被弃用。

建议改用 `a2wsgi` 包，使用方式保持不变。

只要确保已安装 `a2wsgi` 包，并且从 `a2wsgi` 正确导入 `WSGIMiddleware` 即可。
```

**备注**：补充当前推荐从 a2wsgi 导入 WSGIMiddleware、包装后挂载的直接操作证据。

---

## q028 · comparison

**问题**：调用需要 await 的第三方库时，路径操作应该使用 async def 还是普通 def？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：并发 async / await
- 标题路径：并发 async / await > 赶时间吗？
- `document_id`：`doc_dbeb44e6522020e50697ab64`
- `chunk_id`：`chunk_4faee3b8321d58672ad92cea`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/async.md

**证据摘录**

```text
通过 `async def` 声明你的 *路径操作函数*
```

**当前完整 Chunk**

```text
赶时间吗？

<abbr title="too long; didn't read - 太长；没看"><strong>TL;DR:</strong></abbr>

如果你正在使用第三方库，它们会告诉你使用 `await` 关键字来调用它们，就像这样：

results = await some_library()

然后，通过 `async def` 声明你的 *路径操作函数*：

@app.get('/')
async def read_results():
    results = await some_library()
    return results

/// note | 注意

你只能在被 `async def` 创建的函数内使用 `await`。

///

---

如果你正在使用一个第三方库和某些组件（比如：数据库、API、文件系统等）进行通信，而该第三方库不支持使用 `await`（目前大多数数据库库都是这样），这种情况你可以像平常那样使用 `def` 声明一个路径操作函数，就像这样：

@app.get('/')
def results():
    results = some_library()
    return results

如果你的应用程序（以某种方式）不需要与其他任何东西通信而等待其响应，请使用 `async def`，即使函数内部不需要使用 `await`。

如果你不清楚，使用 `def` 就好。

**注意**：你可以根据需要在路径操作函数中混合使用 `def` 和 `async def`，并使用最适合你的方式去定义每个函数。FastAPI 将为它们做正确的事情。

无论如何，在上述任何情况下，FastAPI 仍将异步工作，速度也非常快。

但是，通过遵循上述步骤，它将能够进行一些性能优化。
```

---

## q029 · comparison

**问题**：使用 Pydantic Cookie 参数模型比逐个声明 Cookie 字段多做了什么？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：Cookie 参数模型
- 标题路径：Cookie 参数模型
- `document_id`：`doc_1cb43b5e3ee1074618bb2c7b`
- `chunk_id`：`chunk_3f6d3958d6bef86a07ff393f`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/cookie-param-models.md

**证据摘录**

```text
可以一次性声明所有参数的验证方式和元数据
```

**当前完整 Chunk**

```text
Cookie 参数模型

如果你有一组相关的 **cookie**，你可以创建一个 **Pydantic 模型**来声明它们。🍪

这将允许你在**多个地方**能够**重用模型**，并且可以一次性声明所有参数的验证方式和元数据。😎

/// note | 注意

自 FastAPI 版本 `0.115.0` 起支持此功能。🤓

///

/// tip | 提示

此技术同样适用于 `Query` 、 `Cookie` 和 `Header` 。😎
```

### 候选证据 2

- 建议相关度：`2`
- 文档：Cookie 参数模型
- 标题路径：Cookie 参数模型 > 带有 Pydantic 模型的 Cookie
- `document_id`：`doc_1cb43b5e3ee1074618bb2c7b`
- `chunk_id`：`chunk_9d5bb65c1f9457db83fd3527`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/cookie-param-models.md

**证据摘录**

```text
从请求中接收到的 **cookie** 中**提取**出**每个字段**的数据
```

**当前完整 Chunk**

```text
带有 Pydantic 模型的 Cookie

在 **Pydantic** 模型中声明所需的 **cookie** 参数，然后将参数声明为 `Cookie` ：

{* ../../docs_src/cookie_param_models/tutorial001_an_py310.py hl[9:12,16] *}

**FastAPI** 将从请求中接收到的 **cookie** 中**提取**出**每个字段**的数据，并提供你定义的 Pydantic 模型。
```

### 候选证据 3

- 建议相关度：`2`
- 文档：Cookie 参数模型
- 标题路径：Cookie 参数模型 > 禁止额外的 Cookie
- `document_id`：`doc_1cb43b5e3ee1074618bb2c7b`
- `chunk_id`：`chunk_d8a9570984a010c66979a368`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/cookie-param-models.md

**证据摘录**

```text
禁止（ `forbid` ）任何额外（ `extra` ）字段
```

**当前完整 Chunk**

```text
禁止额外的 Cookie

在某些特殊使用情况下（可能并不常见），你可能希望**限制**你想要接收的 cookie。

你的 API 现在可以控制自己的 <dfn title="只是个玩笑，别当真。和 cookie 同意无关，不过连 API 现在都能拒绝可怜的 cookie，挺好玩的。来，吃块小饼干吧。🍪">cookie 同意</dfn>。🤪🍪

你可以使用 Pydantic 的模型配置来禁止（ `forbid` ）任何额外（ `extra` ）字段：

{* ../../docs_src/cookie_param_models/tutorial002_an_py310.py hl[10] *}

如果客户端尝试发送一些**额外的 cookie**，他们将收到**错误**响应。

可怜的 cookie 通知条，费尽心思为了获得你的同意，却被<dfn title="又是个玩笑，别理我。给你的小饼干配点咖啡吧。☕">API 拒绝了</dfn>。🍪

例如，如果客户端尝试发送一个值为 `good-list-please` 的 `santa_tracker` cookie，客户端将收到一个**错误**响应，告知他们 `santa_tracker` <dfn title="圣诞老人不赞成没有小饼干。🎅 好吧，不再讲 cookie 的笑话了。">cookie 是不允许的</dfn>：

{
    "detail": [
        {
            "type": "extra_forbidden",
            "loc": ["cookie", "santa_tracker"],
            "msg": "Extra inputs are not permitted",
            "input": "good-list-please",
        }
    ]
}
```

**备注**：原 Chunk 只说明字段提取和模型实例化，降为相关度 2；补充模型复用、统一声明验证与元数据的直接收益，以及可禁止额外 Cookie 的辅助能力。

---

## q030 · comparison

**问题**：额外响应的 responses 参数与主响应的 response_model 有什么不同？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：路径操作的高级配置
- 标题路径：路径操作的高级配置 > 附加响应
- `document_id`：`doc_e0ab7b2e23d96d3e541df665`
- `chunk_id`：`chunk_a364f0135665a5d48dfb9144`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/advanced/path-operation-advanced-configuration.md

**证据摘录**

```text
这定义了该 *路径操作* 主响应的元数据
```

**当前完整 Chunk**

```text
附加响应

你可能已经见过如何为一个 *路径操作* 声明 `response_model` 和 `status_code`。

这定义了该 *路径操作* 主响应的元数据。

你也可以为它声明带有各自模型、状态码等的附加响应。

文档中有一个完整章节，你可以阅读这里的[OpenAPI 中的附加响应](additional-responses.md)。
```

### 候选证据 2

- 建议相关度：`2`
- 文档：OpenAPI 中的附加响应
- 标题路径：OpenAPI 中的附加响应 > 带有 `model` 的附加响应
- `document_id`：`doc_666e554d2bafa9d3befaf2c6`
- `chunk_id`：`chunk_4c3d26160279a830638d3990`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/advanced/additional-responses.md

**证据摘录**

```text
传入参数 `responses`
```

**当前完整 Chunk**

```text
带有 `model` 的附加响应

你可以向你的*路径操作装饰器*传入参数 `responses`。

它接收一个 `dict`：键是每个响应的状态码（例如 `200`），值是包含该响应信息的另一个 `dict`。

这些响应的每个 `dict` 都可以有一个键 `model`，包含一个 Pydantic 模型，就像 `response_model` 一样。

**FastAPI** 会获取该模型，生成它的 JSON Schema，并将其放在 OpenAPI 中的正确位置。

例如，要声明另一个状态码为 `404` 且具有 Pydantic 模型 `Message` 的响应，你可以这样写：

{* ../../docs_src/additional_responses/tutorial001_py310.py hl[18,22] *}

/// note | 注意

记住你需要直接返回 `JSONResponse`。

`model` 键不是 OpenAPI 的一部分。

**FastAPI** 会从这里获取 Pydantic 模型，生成 JSON Schema，并把它放到正确的位置。

正确的位置是：

* 在键 `content` 中，它的值是另一个 JSON 对象（`dict`），该对象包含：
* 一个媒体类型作为键，例如 `application/json`，它的值是另一个 JSON 对象，该对象包含：
* 一个键 `schema`，它的值是来自该模型的 JSON Schema，这里就是正确的位置。
* **FastAPI** 会在这里添加一个引用，指向你 OpenAPI 中另一个位置的全局 JSON Schemas，而不是直接内联。这样，其他应用和客户端可以直接使用这些 JSON Schemas，提供更好的代码生成工具等。

为该*路径操作*在 OpenAPI 中生成的响应将是：
```

**备注**：原 Chunk 详细解释 responses 的状态码字典和模型 Schema，但主响应对比不够直接，降为相关度 2；补充明确区分主响应元数据与附加响应的 Chunk。

---
