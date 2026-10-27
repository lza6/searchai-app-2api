# SearchAI 2API — 逆向报告与 Demo

> 目标 App: **SearchAI v1.0.1 Pro Mod**（`com.xjprhinox.searchai`，AI 人物背景调查/深度搜索）
> 上游: `https://appss.airy365.com`（Java Spring, Cloudflare 前置）
> 免责声明: 本仓库仅用于协议安全研究与学习，demo 端口默认只监听本机，请勿用于生产或滥用上游服务。

---

## 一、App 概况

| 项 | 值 |
|---|---|
| 包名 | `com.xjprhinox.searchai` |
| 版本 | 1.0.1 (code 6)，约 11MB，4 dex |
| Mod 签名 | TRUMODS，内置 [ApkSignatureKillerEx](https://github.com/L-JINBIN/ApkSignatureKillerEx)（`bin.mt.signature.KillerApplication`） |
| 业务功能 | 输入人名+生日+地点+职业 → 后端 AI 检索生成学历/家庭/职业/投资/新闻/传记等 9 类背景报告 |
| 第三方 | Google Billing（VIP 付费墙，Mod 已绕过）、AppsFlyer(`2m6YZ4JWe7Liq9EFDbE3x8`)、Firebase(`searchai-1b12c`)、Facebook、boniu 买号 SDK |
| 代码结构 | `com.xjprhinox.searchai`(业务) + `com.xjprhinox.google`(支付/账号) + `com.boniu.baseinfo`(网络层/加密) |

## 二、协议还原（核心成果）

### 2.1 传输加密 — 双 AES-GCM 固定 Key

定义在 `com.xjprhinox.searchai.config.Configuration`：

```
BODY_KEY   = FkdCTuwMcrHyO2LK   # 请求体加密
HEADER_KEY = GQmj8ePOKHn0VN2c   # 请求头 va 加密
APP_NAME   = 10175611458440310241
```

加密格式（`com.boniu.baseinfo.utils.AESUtil`，AES-256-GCM NoPadding）：

```
密文 = base64( nonce[12] || ciphertext || tag[16] )
```

### 2.2 请求格式

**Header**（`ApiHelper.getHeaderMap()`）：

| Header | 值 |
|---|---|
| `n` | APP_NAME |
| `overSeaFlag` | `YES` |
| `sea` | `YES` |
| `va` | HEADER_KEY 加密的设备指纹 JSON：`{deviceType:"ANDROID", version, deviceModel, uuid, brand, channel:"google", appName, lang, region, androidId, systemVersion}` |
| `timeZone` | 如 `Asia/Shanghai` |
| Content-Type | `application/json; charset=utf-8` |

**Body**（所有业务端点统一信封）：

```json
{ "vs": "<BODY_KEY 加密的 JSON>" }
```

明文 JSON 通用字段：`language`、`accountId`（多数端点）、`timestamp`（毫秒字符串）+ 各端点业务字段。

### 2.3 响应格式（XResult）

```json
{ "success": true, "returnCode": "200", "result": {...}, "timeOut": false,
  "errorMsg": "...", "errorMsgEn": "...", /* 12 种语言的错误消息字段 */ }
```

错误时 `returnCode != 200`，`errorStack` 形如 `S20-A0-1003|S08-A1-0000`。

### 2.4 端点清单（已全部实测）

**搜索业务（`/search/ai/*`，代码 `OtherUrl.java`）**

| 端点 | 参数（明文 JSON） | 返回 |
|---|---|---|
| `POST /search/ai/create/task` | `{birthDate, location, professionalBackground, searchTitle}` | `{searchId, status:"RUNNING", searchTitle}` |
| `POST /search/ai/query/task` | `{searchId}` | `{status:"SUCCESS/FAIL", answer:[...]}`（~5s 出结果，App 每 3s 轮询） |
| `POST /search/ai/get/record/detail` | `{searchId}` | 同 query + `evaluation` |
| `POST /search/ai/get/history/page/list` | `{requestPage, pageSize}` | 分页历史 `{totalPage, object:[{searchId, searchTitle}]}` |
| `POST /search/ai/delete/record` | `{searchId}` | — |
| `POST /search/ai/update/record` | `{searchId, evaluation:"GOOD"/"BAD"}` | 点赞/点踩 |

**账号（boniu SDK，`/app/account/*`）**

| 端点 | 说明 |
|---|---|
| `POST /app/account/getAccountInfo` | **body 必须为空**（只带 language/timestamp）——账号由 header `va` 里的 `uuid` 决定，首次调用自动建号；**带 `accountId` 反而报 9990 "please reacquire"** |
| `POST /app/account/quickLogin` | `{token}` |
| `POST /app/account/login/by/password` | `{userName, password}` |

其他 boniu 端点：`/app/product/productList`、`/app/pay/order/create`、`/app/common/uploadFile`、`/app/feedback/*` 等（部分需有效 accountId 会话）。

### 2.5 鉴权模型

- **无 token、无签名、无动态密钥** —— 鉴权完全依赖 header `va` 中的 `uuid`（服务端按 uuid 维持账号）。
- VIP 付费墙只在**客户端**判断（`ApiConfig.getInstance().isVip()`），上游 API 层未校验 VIP —— Mod 版或直接调 API 均可免费 createTask（已验证）。

## 三、实测记录

### 3.1 协议 PoC（probe.py，全部通过）

1. `getAccountInfo` 空 body → 200，自动建号（`dataId: 1017931...`，昵称 U2610518831 形如 `U+uuid后缀`）✅
2. `create/task` → 200 `searchId + RUNNING` ✅
3. `query/task` → `SUCCESS + answer[]` ✅
4. `history/page/list` → 回读任务 ✅
5. 错误 KEY 对照 → 500 NPE（证明解密失败路径）✅

### 3.2 第一轮压测（stress_test.py，demo 端口 8918）

| 场景 | 结果 |
|---|---|
| GET /health | 20/20，median 0.7ms |
| 上游透传（account/history） | 10/10，median 1.0–1.2s，p95 1.8s |
| e2e 真实搜索 x3 并发 | 全部 SUCCESS，wall 6.8s |
| 错误路径 400/404/502 | 全部正确 |
| 上游限流 | x3 并发无 429/无封锁（更高并发未测） |

### 3.3 上游回答质量评估（2026-10-28 批量实测）

9 类预设模板（学历/家庭/职业/投资/新闻/传记/爱好/社交/感情）+ 中英文 + 人名/裸名共 12 组问题，**100% 返回同一句**：

> `"No public information available."`

结论：**上游搜索/LLM 答案引擎当前失效**（协议链路 100% 正常——任务创建、状态流转、历史、账号体系全部工作，仅答案恒为空字符串数组）。这不影响 2API 通道可用性：上游修复后无需改动本 demo 即可直接受益。

### 3.4 踩坑记录

| 坑 | 说明 |
|---|---|
| 跨会话 uuid 失效 | `uuid` 变了服务端就当成新账号，旧 searchId 查不到（跨进程复用 searchId 必须固定 uuid） |
| getAccountInfo 不能带 accountId | 带了返回 9990 "please reacquire"；账号绑定在 header uuid 上 |
| Windows curl | 必须 `--ssl-no-revoke`，否则 CRYPT_E_REVOCATION_OFFLINE 假性连接失败 |
| 根路径 403 | Cloudflare/nginx 对 `/` 返回 403，API 路径正常，不代表服务不可用 |

## 四、Demo Server 使用

```bash
pip install requests cryptography
python demo_server.py 8918          # 默认 8918，0.0.0.0 监听
```

| 接口 | 说明 |
|---|---|
| `GET /` | 中文 demo 页（浏览器直接用） |
| `GET /health` `/stats` | 健康检查 / 统计 |
| `POST /v1/search/ai` | `{prompt, birthDate?, location?, professionalBackground?}` → 同步等待 `answer[]` |
| `POST /v1/search/ai/task` | `{searchId}` → 上游原始查询结果 |
| `POST /v1/search/ai/history` | `{page}` → 历史列表 |
| `POST /v1/account` | 当前 uuid 对应的账号信息 |
| `POST /proxy/<path>` | 任意上游 `/search/ai/*`、`/app/*` 原生透传（自动加解密 vs 信封） |

内置：全局 4 并发闸、uuid 会话自动建号、错误码映射（上游错→502）。

## 五、文件清单

| 文件 | 说明 |
|---|---|
| `demo_server.py` | 2API demo 服务（Python 标准库 HTTP + cryptography） |
| `demo.html` | 中文操作面板 |
| `probe.py` | 协议 PoC（可独立验证上游） |
| `stress_test.py` | 压测脚本（基线/错误路径/e2e 并发） |

## 六、new-api 渠道对接（待指示）

上游答案引擎恢复前，对接 new-api 的价值主要是任务型渠道模板（create/query 两段式）。等下游网关接入指示后按 type 渠道规范落地。
