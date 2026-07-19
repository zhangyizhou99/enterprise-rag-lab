# fastapi_retrieval_v1 人工审核 1-5

- 语料快照：`vector_f8c4ccfbd78b2742ec7956a7`
- 数据集哈希：`f3061103f733b7e717c803893d80f5fd8714c70e6321cd7f971f00707a6180b5`
- 本批题数：5
- 说明：以下相关度是种子建议，不是人工结论。逐题确认后才能将 `review_status` 改为 `approved`。
- 审核对象：本阶段只评估“问题 → Chunk”的检索相关性，尚未生成答案。请判断完整 Chunk 是否含有足以支撑回答的事实，不需要撰写标准答案、查找 ID 或自行搜索语料库。

相关度口径：`3` 直接完整回答；`2` 部分回答或重要辅助证据；`1` 弱相关；不相关则删除该 judgment。

## q001 · configuration

**问题**：如何在 FastAPI 中配置允许跨域访问的源、方法和请求头？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：CORS（跨域资源共享）
- 标题路径：CORS（跨域资源共享） > 使用 `CORSMiddleware`
- `document_id`：`doc_09318da6570045fe6fa6e5e0`
- `chunk_id`：`chunk_47bac0dc3f2b85de07b15a84`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/cors.md

**证据摘录**

```text
CORSMiddleware
```

**当前完整 Chunk**

```text
使用 `CORSMiddleware`

你可以在 **FastAPI** 应用中使用 `CORSMiddleware` 来配置它。

* 导入 `CORSMiddleware`。
* 创建一个允许的源列表（由字符串组成）。
* 将其作为「中间件」添加到你的 **FastAPI** 应用中。

你也可以指定后端是否允许：

* 凭证（Authorization 请求头、Cookies 等）。
* 特定的 HTTP 方法（`POST`，`PUT`）或者使用通配符 `"*"` 允许所有方法。
* 特定的 HTTP 请求头或者使用通配符 `"*"` 允许所有请求头。

{* ../../docs_src/cors/tutorial001_py310.py hl[2,6:11,13:19] *}

默认情况下，这个 `CORSMiddleware` 实现所使用的默认参数较为保守，所以你需要显式地启用特定的源、方法或者 headers，以便浏览器能够在跨域上下文中使用它们。

支持以下参数：
```

---

## q002 · configuration

**问题**：添加多个 FastAPI 中间件时，请求和响应的执行顺序是什么？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：中间件
- 标题路径：中间件 > 多个中间件的执行顺序
- `document_id`：`doc_8bfb4c03599bfaa8043ca0cb`
- `chunk_id`：`chunk_14eea279a252f8231c9a0698`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/middleware.md

**证据摘录**

```text
最后添加的中间件是“最外层”的
```

**当前完整 Chunk**

```text
多个中间件的执行顺序

当你使用 `@app.middleware()` 装饰器或 `app.add_middleware()` 方法添加多个中间件时，每个新中间件都会包裹应用，形成一个栈。最后添加的中间件是“最外层”的，最先添加的是“最内层”的。

在请求路径上，最外层的中间件先运行。

在响应路径上，它最后运行。

例如：

app.add_middleware(MiddlewareA)
app.add_middleware(MiddlewareB)

这会产生如下执行顺序：

* 请求：MiddlewareB → MiddlewareA → 路由

* 响应：路由 → MiddlewareA → MiddlewareB

这种栈式行为确保中间件按可预测且可控的顺序执行。
```

---

## q003 · configuration

**问题**：如何用 Pydantic Settings 从环境变量读取并校验 FastAPI 配置？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：设置和环境变量
- 标题路径：设置和环境变量 > Pydantic 的 `Settings` > 创建 `Settings` 对象
- `document_id`：`doc_451f81e6883c75d70365418d`
- `chunk_id`：`chunk_85e625311f3f8a922a1ceaa5`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/advanced/settings.md

**证据摘录**

```text
Pydantic 会以不区分大小写的方式读取环境变量
```

**当前完整 Chunk**

```text
创建 `Settings` 对象

从 Pydantic 导入 `BaseSettings` 并创建一个子类，这与创建 Pydantic 模型非常相似。

与 Pydantic 模型一样，用类型注解声明类属性，也可以指定默认值。

你可以使用与 Pydantic 模型相同的验证功能和工具，例如不同的数据类型，以及使用 `Field()` 进行附加验证。

{* ../../docs_src/settings/tutorial001_py310.py hl[2,5:8,11] *}

如果你想要一个可以快速复制粘贴的示例，请不要使用这个示例，使用下面最后一个示例。

当你创建该 `Settings` 类的实例（此处是 `settings` 对象）时，Pydantic 会以不区分大小写的方式读取环境变量，因此，大写变量 `APP_NAME` 仍会用于属性 `app_name`。

接着它会转换并验证数据。因此，当你使用该 `settings` 对象时，你将获得你声明的类型的数据（例如 `items_per_user` 将是 `int`）。
```

---

## q004 · configuration

**问题**：部署 FastAPI 时，通常由什么组件处理 HTTPS 证书并把请求转给应用？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：关于 HTTPS
- 标题路径：关于 HTTPS
- `document_id`：`doc_7516b7bd9c64f9831ad770d2`
- `chunk_id`：`chunk_76dac934743c34725fa73124`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/deployment/https.md

**证据摘录**

```text
TLS 终止代理
```

**当前完整 Chunk**

```text
通常的做法是在服务器上运行**一个程序/HTTP 服务器**并**管理所有 HTTPS 部分**：接收**加密的 HTTPS 请求**， 将 **解密的 HTTP 请求** 发送到在同一服务器中运行的实际 HTTP 应用程序（在本例中为 **FastAPI** 应用程序），从应用程序中获取 **HTTP 响应**， 使用适当的 **HTTPS 证书**对其进行加密并使用 **HTTPS** 将其发送回客户端。 此服务器通常被称为 **[TLS 终止代理(TLS Termination Proxy)](https://en.wikipedia.org/wiki/TLS_termination_proxy)**。

你可以用作 TLS 终止代理的一些选项包括：

* Traefik（也可以处理证书更新）
* Caddy（也可以处理证书更新）
* Nginx
* HAProxy
```

---

## q005 · configuration

**问题**：FastAPI 位于可信代理后面时，怎样让 HTTPS 重定向生成正确的公网 URL？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：使用代理
- 标题路径：使用代理 > 代理转发的请求头 > 使用 HTTPS 的重定向
- `document_id`：`doc_4d66f266c40d8a3e7b03e4e6`
- `chunk_id`：`chunk_d64ee05fa282540853e319cb`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/advanced/behind-a-proxy.md

**证据摘录**

```text
通过设置 `--proxy-headers`
```

**当前完整 Chunk**

```text
使用 HTTPS 的重定向

例如，假设你定义了一个*路径操作* `/items/`：

{* ../../docs_src/behind_a_proxy/tutorial001_01_py310.py hl[6] *}

如果客户端尝试访问 `/items`，默认会被重定向到 `/items/`。

但在设置 *CLI 选项* `--forwarded-allow-ips` 之前，它可能会重定向到 `http://localhost:8000/items/`。

而你的应用可能托管在 `https://mysuperapp.com`，重定向应当是 `https://mysuperapp.com/items/`。

通过设置 `--proxy-headers`，FastAPI 现在就可以重定向到正确的位置。😎

https://mysuperapp.com/items/

/// tip | 提示

如果你想了解更多关于 HTTPS 的内容，查看指南：[关于 HTTPS](../deployment/https.md)。
```

---
