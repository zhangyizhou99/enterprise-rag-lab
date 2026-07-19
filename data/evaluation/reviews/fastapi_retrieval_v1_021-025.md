# fastapi_retrieval_v1 人工审核 21-25

- 语料快照：`vector_f8c4ccfbd78b2742ec7956a7`
- 数据集哈希：`34e73f61d3312477d51dcca1e744219076aae29063d297f6819e2d3ce705b017`
- 本批题数：5
- 说明：以下相关度是种子建议，不是人工结论。逐题确认后才能将 `review_status` 改为 `approved`。
- 审核对象：本阶段只评估“问题 → Chunk”的检索相关性，尚未生成答案。请判断完整 Chunk 是否含有足以支撑回答的事实，不需要撰写标准答案、查找 ID 或自行搜索语料库。

相关度口径：`3` 直接完整回答；`2` 部分回答或重要辅助证据；`1` 弱相关；不相关则删除该 judgment。

## q021 · troubleshooting

**问题**：JSON 请求缺少 Content-Type 时为什么不会按 JSON 解析？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：严格的 Content-Type 检查
- 标题路径：严格的 Content-Type 检查
- `document_id`：`doc_498de5ed55bac50d2f1dd82a`
- `chunk_id`：`chunk_72c5393a45809269ea513c53`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/advanced/strict-content-type.md

**证据摘录**

```text
JSON 请求必须包含有效的 `Content-Type` 头
```

**当前完整 Chunk**

```text
严格的 Content-Type 检查

默认情况下，FastAPI 对 JSON 请求体使用严格的 `Content-Type` 头检查。这意味着，JSON 请求必须包含有效的 `Content-Type` 头（例如 `application/json`），其请求体才会被按 JSON 解析。
```

---

## q022 · troubleshooting

**问题**：FastAPI 安全工具认证失败为什么现在返回 401 而不是旧版 403？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：使用旧的 403 认证错误状态码
- 标题路径：使用旧的 403 认证错误状态码
- `document_id`：`doc_937783b9078cbb64f23bbcfa`
- `chunk_id`：`chunk_3c779dd3f98e788dae94158c`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/how-to/authentication-error-status-code.md

**证据摘录**

```text
`401 Unauthorized`
```

**当前完整 Chunk**

```text
使用旧的 403 认证错误状态码

在 FastAPI `0.122.0` 版本之前，当内置的安全工具在认证失败后向客户端返回错误时，会使用 HTTP 状态码 `403 Forbidden`。

从 FastAPI `0.122.0` 版本开始，它们改用更合适的 HTTP 状态码 `401 Unauthorized`，并在响应中返回合理的 `WWW-Authenticate` 头，遵循 HTTP 规范，[RFC 7235](https://datatracker.ietf.org/doc/html/rfc7235#section-3.1)、[RFC 9110](https://datatracker.ietf.org/doc/html/rfc9110#name-401-unauthorized)。

但如果由于某些原因你的客户端依赖旧行为，你可以在你的安全类中重写方法 `make_not_authenticated_error` 来回退到旧行为。

例如，你可以创建一个 `HTTPBearer` 的子类，使其返回 `403 Forbidden` 错误，而不是默认的 `401 Unauthorized` 错误：

{* ../../docs_src/authentication_error_status_code/tutorial001_an_py310.py hl[9:13] *}

/// tip | 提示

注意该函数返回的是异常实例，而不是直接抛出它。抛出操作由其余的内部代码完成。

///
```

---

## q023 · troubleshooting

**问题**：测试时怎样临时替换 FastAPI 依赖并在结束后恢复？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：使用覆盖测试依赖项
- 标题路径：使用覆盖测试依赖项 > 测试时覆盖依赖项 > 使用 `app.dependency_overrides` 属性
- `document_id`：`doc_3b8b29f79e7494dff9b99a02`
- `chunk_id`：`chunk_847b57ff3dceeb1bc9654260`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/advanced/testing-dependencies.md

**证据摘录**

```text
app.dependency_overrides
```

**当前完整 Chunk**

```text
使用 `app.dependency_overrides` 属性

对于这些用例，**FastAPI** 应用支持 `app.dependency_overrides` 属性，该属性就是**字典**。

要在测试时覆盖原有依赖项，这个字典的键应当是原依赖项（函数），值是覆盖依赖项（另一个函数）。

这样一来，**FastAPI** 就会调用覆盖依赖项，不再调用原依赖项。

{* ../../docs_src/dependency_testing/tutorial001_an_py310.py hl[26:27,30] *}

/// tip | 提示

**FastAPI** 应用中的任何位置都可以实现覆盖依赖项。

原依赖项可用于*路径操作函数*、*路径操作装饰器*（不需要返回值时）、`.include_router()` 调用等。

FastAPI 可以覆盖这些位置的依赖项。

///

然后，使用 `app.dependency_overrides` 把覆盖依赖项重置为空**字典**：

app.dependency_overrides = {}

如果只在某些测试时覆盖依赖项，您可以在测试开始时（在测试函数内）设置覆盖依赖项，并在结束时（在测试函数结尾）重置覆盖依赖项。
```

---

## q024 · troubleshooting

**问题**：CORS 开启凭证后为什么不能把 origins、methods 和 headers 都设为通配符？

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
- `chunk_id`：`chunk_0291cf68753b757c380c1d39`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/cors.md

**证据摘录**

```text
`allow_credentials` 设为 `True` 时
```

**当前完整 Chunk**

```text
* `allow_origins` - 一个允许跨域请求的源列表。例如 `['https://example.org', 'https://www.example.org']`。你可以使用 `['*']` 允许任何源。
* `allow_origin_regex` - 一个正则表达式字符串，匹配的源允许跨域请求。例如 `'https://.*\.example\.org'`。
* `allow_methods` - 一个允许跨域请求的 HTTP 方法列表。默认为 `['GET']`。你可以使用 `['*']` 来允许所有标准方法。
* `allow_headers` - 一个允许跨域请求的 HTTP 请求头列表。默认为 `[]`。你可以使用 `['*']` 允许所有的请求头。`Accept`、`Accept-Language`、`Content-Language` 以及 `Content-Type` 这几个请求头在[简单 CORS 请求](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS#simple_requests)中总是被允许。
* `allow_credentials` - 指示跨域请求支持 cookies。默认是 `False`。

当 `allow_credentials` 设为 `True` 时，`allow_origins`、`allow_methods` 和 `allow_headers` 都不能设为 `['*']`。它们必须[显式指定](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS#credentialed_requests_and_wildcards)。

* `expose_headers` - 指示可以被浏览器访问的响应头。默认为 `[]`。
* `max_age` - 设定浏览器缓存 CORS 响应的最长时间，单位是秒。默认为 `600`。
```

### 候选证据 2

- 建议相关度：`2`
- 文档：CORS（跨域资源共享）
- 标题路径：CORS（跨域资源共享） > 通配符
- `document_id`：`doc_09318da6570045fe6fa6e5e0`
- `chunk_id`：`chunk_8d829c7320e1dc36e25a2625`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/cors.md

**证据摘录**

```text
不包括所有涉及凭据的内容
```

**当前完整 Chunk**

```text
通配符

也可以使用 `"*"`（一个「通配符」）声明这个列表，表示全部都是允许的。

但这仅允许某些类型的通信，不包括所有涉及凭据的内容：比如 Cookies，以及那些使用 Bearer 令牌的 Authorization 请求头等。

因此，为了一切都能正常工作，最好显式地指定允许的源。
```

**备注**：原 Chunk 精确给出启用凭证时三项必须显式指定的规则；补充同文档中解释通配符不覆盖凭证通信的原因 Chunk。

---

## q025 · comparison

**问题**：返回字典或数据库对象时，response_model 与函数返回类型应该怎样选择？

**当前状态**：`approved`

- [ ] 问题自然且含义明确
- [ ] 完整 Chunk 含有足以支撑回答的事实
- [ ] 相关度等级合理
- 可选备注：你若明显想到其他正确证据可以指出；无需自行查库
- 决定：`通过 / 修改 / 删除`

### 候选证据 1

- 建议相关度：`3`
- 文档：响应模型 - 返回类型
- 标题路径：响应模型 - 返回类型 > `response_model` 参数
- `document_id`：`doc_02f5b855e9a90b2aaf851f88`
- `chunk_id`：`chunk_6f448335e70200b32dd4a558`
- 来源：https://github.com/fastapi/fastapi/blob/afe41126f624af30038cc8e17b2aaf60ebd4b838/docs/zh/docs/tutorial/response-model.md

**证据摘录**

```text
参数 `response_model`，而不是返回类型
```

**当前完整 Chunk**

```text
`response_model` 参数

在一些情况下，你需要或希望返回的数据与声明的类型不完全一致。

例如，你可能希望**返回一个字典**或数据库对象，但**将其声明为一个 Pydantic 模型**。这样 Pydantic 模型就会为你返回的对象（例如字典或数据库对象）完成文档、校验等工作。

如果你添加了返回类型注解，工具和编辑器会（正确地）报错，提示你的函数返回的类型（例如 `dict`）与声明的类型（例如一个 Pydantic 模型）不同。

在这些情况下，你可以使用*路径操作装饰器*参数 `response_model`，而不是返回类型。

你可以在任意*路径操作*中使用 `response_model` 参数：

* `@app.get()`
* `@app.post()`
* `@app.put()`
* `@app.delete()`
* 等等。

{* ../../docs_src/response_model/tutorial001_py310.py hl[17,22,24:27] *}

/// note | 注意

注意，`response_model` 是「装饰器」方法（`get`、`post` 等）的一个参数。不是你的*路径操作函数*的参数，不像所有查询参数和请求体那样。

///

`response_model` 接收的类型与为 Pydantic 模型字段声明的类型相同，因此它可以是一个 Pydantic 模型，也可以是一个由 Pydantic 模型组成的 `list`，例如 `List[Item]`。

FastAPI 会使用这个 `response_model` 来完成数据文档、校验等，并且还会将输出数据**转换并过滤**为其类型声明。

/// tip | 提示

如果你的编辑器、mypy 等进行严格类型检查，你可以将函数返回类型声明为 `Any`。
```

---
