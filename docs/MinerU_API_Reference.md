# 单个文件解析

## 创建解析任务

### 接口说明
适用于通过 API 创建解析任务的场景，用户须先申请 Token。

**注意：**
*   单个文件大小不能超过 200MB，文件页数不超出 600 页
*   每个账号每天享有 2000 页最高优先级解析额度，超过 2000 页的部分优先级降低
*   因网络限制，github、aws 等国外 URL 会请求超时
*   该接口不支持文件直接上传
*   header 头中需要包含 `Authorization` 字段，格式为 `Bearer + 空格 + Token`

### Python 请求示例

```python
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/extract/task"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
    "model_version": "vlm"
}

res = requests.post(url, headers=header, json=data)
print(res.status_code)
print(res.json())
print(res.json()["data"])
```

### CURL 请求示例

```bash
curl --location --request POST 'https://mineru.net/api/v4/extract/task' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "url": "https://cdn-mineru.openxlab.org.cn/demo/example.pdf",
    "model_version": "vlm"
}'
```

### 请求体参数说明

| 参数 | 类型 | 是否必选 | 示例 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| **url** | string | 是 | `https://.../demo.pdf` | 文件 URL，支持 .pdf, .doc, .docx, .ppt, .pptx, .png, .jpg, .jpeg 多种格式 |
| **is_ocr** | bool | 否 | `false` | 是否启动 ocr 功能，默认 false，仅对 pipeline 模型有效 |
| **enable_formula** | bool | 否 | `true` | 是否开启公式识别，默认 true，仅对 pipeline 模型有效 |
| **enable_table** | bool | 否 | `true` | 是否开启表格识别，默认 true，仅对 pipeline 模型有效 |
| **language** | string | 否 | `ch` | 指定文档语言，默认 ch，仅对 pipeline 模型有效。[可选值参考](https://www.paddleocr.ai/latest/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html#_3) |
| **data_id** | string | 否 | `abc**` | 解析对象对应的数据 ID。由字母、数字、下划线、短划线、句号组成，不超过 128 字符。 |
| **callback** | string | 否 | `http://127.0.0.1/callback` | 解析结果回调通知 URL。必须支持 POST、UTF-8、JSON。参数包含 `checksum` 和 `content`。 |
| **seed** | string | 否 | `abc**` | 随机字符串（<64字符），用于回调签名校验。**使用 callback 时必填。** |
| **extra_formats** | [string] | 否 | `["docx","html"]` | 额外导出格式，支持 docx, html, latex。markdown 和 json 为默认导出格式。 |
| **page_ranges** | string | 否 | `1-600` | 指定页码范围。例："2,4-6" 或 "2--2"（倒数第二页）。 |
| **model_version** | string | 否 | `vlm` | 模型版本，可选 `pipeline` 或 `vlm`，默认 `pipeline`。 |

**回调说明 (Callback):**
*   **checksum**: SHA256(uid + seed + content)。
*   **content**: JSON 字符串，结构同“任务查询结果”的 data 部分。
*   **响应**: 服务端应返回 HTTP 200，否则重试 5 次。

### 请求体示例

```json
{
  "url": "https://static.openxlab.org.cn/opendatalab/pdf/demo.pdf",
  "model_version": "vlm",
  "data_id": "abcd"
}
```

### 响应参数说明

| 参数 | 类型 | 示例 | 说明 |
| :--- | :--- | :--- | :--- |
| **code** | int | 0 | 接口状态码，成功：0 |
| **msg** | string | ok | 接口处理信息，成功："ok" |
| **trace_id** | string | c876cd... | 请求 ID |
| **data.task_id** | string | a90e6a... | 提取任务 id，可用于查询任务结果 |

### 响应示例

```json
{
  "code": 0,
  "data": {
    "task_id": "a90e6ab6-44f3-4554-b4***"
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

---

## 获取任务结果

### 接口说明
通过 `task_id` 查询提取任务目前的进度，任务处理完成后，接口会响应对应的提取详情。

### Python 请求示例

```python
import requests

token = "官网申请的api token"
task_id = "你的task_id"
url = f"https://mineru.net/api/v4/extract/task/{task_id}"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

res = requests.get(url, headers=header)
print(res.status_code)
print(res.json())
print(res.json()["data"])
```

### CURL 请求示例

```bash
curl --location --request GET 'https://mineru.net/api/v4/extract/task/{task_id}' \
--header 'Authorization: Bearer *****' \
--header 'Accept: */*'
```

### 响应参数说明

| 参数 | 类型 | 示例 | 说明 |
| :--- | :--- | :--- | :--- |
| **code** | int | 0 | 接口状态码，成功：0 |
| **msg** | string | ok | 接口处理信息 |
| **trace_id** | string | ... | 请求 ID |
| **data.task_id** | string | abc** | 任务 ID |
| **data.data_id** | string | abc** | 解析对象对应的数据 ID |
| **data.state** | string | done | 状态：`done` (完成), `pending` (排队), `running` (解析中), `failed` (失败), `converting` (转换中) |
| **data.full_zip_url** | string | https://... | 结果压缩包 URL。[文件说明参考](https://opendatalab.github.io/MinerU/reference/output_files/) |
| **data.err_msg** | string | ... | 解析失败原因 (state=failed 时有效) |
| **data.extract_progress** | object | - | 进度详情 (state=running 时有效) |
| - extracted_pages | int | 1 | 已解析页数 |
| - total_pages | int | 2 | 总页数 |
| - start_time | string | 2025-01... | 开始时间 |

### 响应示例

**正在运行中 (Running):**
```json
{
  "code": 0,
  "data": {
    "task_id": "47726b6e-46ca-4bb9-******",
    "state": "running",
    "err_msg": "",
    "extract_progress": {
      "extracted_pages": 1,
      "total_pages": 2,
      "start_time": "2025-01-20 11:43:20"
    }
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

**完成 (Done):**
```json
{
  "code": 0,
  "data": {
    "task_id": "47726b6e-46ca-4bb9-******",
    "state": "done",
    "full_zip_url": "https://cdn-mineru.openxlab.org.cn/pdf/018e53ad-d4f1-475d-b380-36bf24db9914.zip",
    "err_msg": ""
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

---

# 批量文件解析

## 文件批量上传解析

### 接口说明
适用于本地文件上传解析的场景，可通过此接口批量申请文件上传链接，上传文件后，系统会自动提交解析任务。

**注意：**
*   申请的文件上传链接有效期为 24 小时。
*   上传文件时，无须设置 Content-Type 请求头。
*   文件上传完成后，**无须**调用提交解析任务接口，系统会自动扫描并提交。
*   单次申请链接不能超过 200 个。
*   header 头中需要包含 `Authorization` 字段。

### Python 请求示例

```python
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/file-urls/batch"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "files": [
        {"name":"demo.pdf", "data_id": "abcd"}
    ],
    "model_version":"vlm"
}
file_path = ["demo.pdf"]
try:
    response = requests.post(url, headers=header, json=data)
    if response.status_code == 200:
        result = response.json()
        print('response success. result:{}'.format(result))
        if result["code"] == 0:
            batch_id = result["data"]["batch_id"]
            urls = result["data"]["file_urls"]
            print('batch_id:{},urls:{}'.format(batch_id, urls))
            for i in range(0, len(urls)):
                with open(file_path[i], 'rb') as f:
                    res_upload = requests.put(urls[i], data=f)
                    if res_upload.status_code == 200:
                        print(f"{urls[i]} upload success")
                    else:
                        print(f"{urls[i]} upload failed")
        else:
            print('apply upload url failed, reason:{}'.format(result["msg"]))
    else:
        print('response not success. status:{} ,result:{}'.format(response.status_code, response))
except Exception as err:
    print(err)
```

### CURL 请求示例

**1. 申请上传链接:**
```bash
curl --location --request POST 'https://mineru.net/api/v4/file-urls/batch' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "files": [
        {"name":"demo.pdf", "data_id": "abcd"}
    ],
    "model_version": "vlm"
}'
```

**2. 文件上传:**
```bash
curl -X PUT -T /path/to/your/file.pdf 'https://****'
```

### 请求体参数说明

| 参数 | 类型 | 是否必选 | 示例 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| **file.name** | string | 是 | `demo.pdf` | 文件名，支持 pdf, doc, docx, ppt, pptx, png, jpg, jpeg |
| **file.is_ocr** | bool | 否 | `true` | 是否启动 ocr (pipeline 模型) |
| **file.data_id** | string | 否 | `abc**` | 数据 ID |
| **file.page_ranges** | string | 否 | `1-600` | 页码范围 |
| **enable_formula** | bool | 否 | `true` | 开启公式识别 (pipeline 模型) |
| **enable_table** | bool | 否 | `true` | 开启表格识别 (pipeline 模型) |
| **language** | string | 否 | `ch` | 文档语言 (pipeline 模型) |
| **callback** | string | 否 | - | 回调 URL |
| **seed** | string | 否 | - | 回调签名随机串 |
| **extra_formats** | [string] | 否 | `["docx"]` | 额外导出格式 |
| **model_version** | string | 否 | `vlm` | 模型版本 (pipeline/vlm) |

### 响应示例

```json
{
  "code": 0,
  "data": {
    "batch_id": "2bb2f0ec-a336-4a0a-b61a-241afaf9cc87",
    "file_urls": [
        "https://mineru.oss-cn-shanghai.aliyuncs.com/api-upload/***"
    ]
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

---

## URL 批量上传解析

### 接口说明
适用于通过 API 批量创建提取任务的场景。

**注意：**
*   单次申请链接不能超过 200 个
*   文件大小不能超过 200MB，文件页数不超出 600 页
*   github、aws 等国外 URL 可能请求超时

### Python 请求示例

```python
import requests

token = "官网申请的api token"
url = "https://mineru.net/api/v4/extract/task/batch"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}
data = {
    "files": [
        {"url":"https://cdn-mineru.openxlab.org.cn/demo/example.pdf", "data_id": "abcd"}
    ],
    "model_version": "vlm"
}
try:
    response = requests.post(url, headers=header, json=data)
    if response.status_code == 200:
        result = response.json()
        if result["code"] == 0:
            print('batch_id:{}'.format(result["data"]["batch_id"]))
        else:
            print('submit task failed, reason:{}'.format(result["msg"]))
    else:
        print('response not success')
except Exception as err:
    print(err)
```

### CURL 请求示例

```bash
curl --location --request POST 'https://mineru.net/api/v4/extract/task/batch' \
--header 'Authorization: Bearer ***' \
--header 'Content-Type: application/json' \
--header 'Accept: */*' \
--data-raw '{
    "files": [
        {"url":"https://cdn-mineru.openxlab.org.cn/demo/example.pdf", "data_id": "abcd"}
    ],
    "model_version": "vlm"
}'
```

### 请求体参数说明

参数与“文件批量上传解析”类似，区别在于 `file` 对象中使用 `url` 而非 `name`。

| 参数 | 类型 | 是否必选 | 示例 | 描述 |
| :--- | :--- | :--- | :--- | :--- |
| **file.url** | string | 是 | `http://...` | 文件链接 |
| **file.data_id** | string | 否 | `abc**` | 数据 ID |
| ... | ... | ... | ... | 其他参数同上 |

### 响应示例

```json
{
  "code": 0,
  "data": {
    "batch_id": "2bb2f0ec-a336-4a0a-b61a-241afaf9cc87"
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

---

## 批量获取任务结果

### 接口说明
通过 `batch_id` 批量查询提取任务的进度。

### Python 请求示例

```python
import requests

token = "官网申请的api token"
batch_id = "你的batch_id"
url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

res = requests.get(url, headers=header)
print(res.status_code)
print(res.json())
```

### CURL 请求示例

```bash
curl --location --request GET 'https://mineru.net/api/v4/extract-results/batch/{batch_id}' \
--header 'Authorization: Bearer *****' \
--header 'Accept: */*'
```

### 响应参数说明

| 参数 | 类型 | 示例 | 说明 |
| :--- | :--- | :--- | :--- |
| **code** | int | 0 | 成功：0 |
| **data.batch_id** | string | ... | 批量任务 ID |
| **data.extract_result** | list | - | 结果列表 |
| - file_name | string | demo.pdf | 文件名 |
| - state | string | done | 状态，新增 `waiting-file` (等待上传) |
| - full_zip_url | string | ... | 结果 URL |
| - err_msg | string | ... | 错误信息 |
| - data_id | string | ... | 数据 ID |

### 响应示例

```json
{
  "code": 0,
  "data": {
    "batch_id": "2bb2f0ec-a336-4a0a-b61a-241afaf9cc87",
    "extract_result": [
      {
        "file_name": "example.pdf",
        "state": "done",
        "err_msg": "",
        "full_zip_url": "https://cdn-mineru.openxlab.org.cn/pdf/018e53ad-d4f1-475d-b380-36bf24db9914.zip"
      },
      {
        "file_name":"demo.pdf",
        "state": "running",
        "err_msg": "",
        "extract_progress": {
          "extracted_pages": 1,
          "total_pages": 2,
          "start_time": "2025-01-20 11:43:20"
        }
      }
    ]
  },
  "msg": "ok",
  "trace_id": "c876cd60b202f2396de1f9e39a1b0172"
}
```

---

# 常见错误码

| 错误码 | 说明 | 解决建议 |
| :--- | :--- | :--- |
| **A0202** | Token 错误 | 检查 Token 是否正确，是否有 Bearer 前缀，或更换新 Token |
| **A0211** | Token 过期 | 更换新 Token |
| **-500** | 传参错误 | 请确保参数类型及 Content-Type 正确 |
| **-10001** | 服务异常 | 请稍后再试 |
| **-10002** | 请求参数错误 | 检查请求参数格式 |
| **-60001** | 生成上传 URL 失败 | 请稍后再试 |
| **-60002** | 获取匹配的文件格式失败 | 检测文件类型失败，确保文件后缀名正确 (pdf, doc, docx, ppt, pptx, png, jpg, jpeg) |
| **-60003** | 文件读取失败 | 请检查文件是否损坏并重新上传 |
| **-60004** | 空文件 | 请上传有效文件 |
| **-60005** | 文件大小超出限制 | 检查文件大小，最大支持 200MB |
| **-60006** | 文件页数超过限制 | 请拆分文件后重试 (<600页) |
| **-60007** | 模型服务暂时不可用 | 请稍后重试或联系技术支持 |
| **-60008** | 文件读取超时 | 检查 URL 可访问性 |
| **-60009** | 任务提交队列已满 | 请稍后再试 |
| **-60010** | 解析失败 | 请稍后再试 |
| **-60011** | 获取有效文件失败 | 请确保文件已上传 |
| **-60012** | 找不到任务 | 请确保 task_id 有效且未删除 |
| **-60013** | 没有权限访问该任务 | 只能访问自己提交的任务 |
| **-60014** | 删除运行中的任务 | 运行中的任务暂不支持删除 |
| **-60015** | 文件转换失败 | 可以手动转为 pdf 再上传 |
| **-60016** | 文件转换失败 | 文件转换为指定格式失败，可以尝试其他格式导出或重试 |