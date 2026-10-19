---
title: OpenID Connect 与身份令牌
slug: openid-connect-and-id-tokens
module: traditional-solutions
stage: design
type: core
difficulty: intermediate
duration: 50m
prerequisites:
  - oauth2-flows-and-pkce
outcomes:
  - 说明 OIDC 在 OAuth 2.0 之上补了哪些产物，并判断一次登录该不该用 OIDC
  - 写出 RP 侧校验 ID Token 的完整检查顺序，并说明漏掉 aud、nonce 各自会导致什么
  - 区分 RP 会话、OP 会话与前端/后端通道登出，为一次“真正的退出”排出步骤
last_reviewed: 2026-10-19
---

# OpenID Connect 与身份令牌

## 为什么需要学习

晴空商城的登录原本只有顾客手机号加密码一个入口。现在要接三处新的：四十名客服必须用公司账号加第二因素登录退款后台，三家仓储供应商要登录发货看板，顾客端还要支持微信登录。团队很自然地想：OAuth 已经接好了，拿到 access token 就知道是谁，直接用它建会话吧。

两周后出了三个问题。客服后台把 access token 里的 `user_id` 当身份，身份平台换实现后该字段换了编号，四十名客服全被认成同一个人；顾客用未验证邮箱注册，登录后被并入别人的历史订单；采购部在共享电脑上点了“退出”，第二天新使用者只点一下“登录”就进了退款后台。

根源是同一个误判：把“应用被授权调用接口”当成了“这个人已被认证”。

> **核心结论：** OAuth 2.0 授予的是“你的应用能调用什么”，OIDC 才回答“这次登录的人是谁”；把 access token 当身份来源，是把授权委托误当成认证。

## 学习目标

完成本课后，你能够：

- 说明 OIDC 在 OAuth 2.0 之上新增的产物（`openid` 范围、ID Token、UserInfo、Discovery）。
- 写出 RP 侧校验 ID Token 的检查顺序，解释顺序为何不能调整，并说明漏掉某项时攻击者能做什么。
- 区分 RP 会话、OP 会话与两种登出通道，排出“共享电脑上真正退出”的步骤。
- 为晴空商城的登录在 OIDC、纯 OAuth 与 SAML 之间做出选择并说明代价。

## 前置知识

- 回看上一课：[OAuth 2.0 授权流程与 PKCE](04-oauth2-flows-and-pkce.md)。
- 知道 JWT 是 `header.payload.signature` 三段 base64url 编码，签名只证明未被篡改，不等于加密。
- 知道授权码流程里 `state` 与 `redirect_uri` 的作用。
- 能读懂 Python 3 的字典、函数与 `hmac` 模块的基本用法。

## 业务场景

晴空商城把登录统一交给身份平台 `https://login.qingkong.example`，它成为唯一身份权威，商城侧应用都变成 *RP*。三个接入面要求不同：

- **退款后台 `refund-portal`**：每次退款要以“具体的人”留痕；单笔超 500 元的审批要求“五分钟内刚做过第二因素”。
- **顾客端商城**：一台手机可能多人使用，退出后再点“我的订单”必须重新输入凭据。
- **仓储发货看板**：三家供应商只能看自己的发货单，不想维护密码，只要一个跳转登录。
- **离职与换岗**：人事禁用账号后，退款后台的现有会话必须几分钟内失效，且不能被静默恢复。

评审会要回答：靠哪个字段认人？哪些字段必须校验？“退出”清掉谁的状态？

## 核心概念

*OpenID Connect*（OIDC）是 OAuth 2.0 之上的认证层：复用同一套授权码流程，只多规定“怎样把认证结果告诉客户端”。*OpenID Provider*（*OP*）负责认证用户，即身份平台；*Relying Party*（*RP*）信任 OP 的结论并据此建立登录态。

*ID Token* 是 OP 签发、供客户端自己读的 JWT，声明“这次认证发生了什么”。它与 access token 的差别在受众：后者给资源服务器，前者写给 RP。*声明*（claim）是这封信的字段。

*sub* 是 OP 内稳定的主体标识，也是 RP 唯一该用来关联本地账号的键。*nonce* 是 RP 发起登录时生成的一次性值，OP 原样放进 ID Token，证明“对应我发起的那次登录”。*UserInfo* 换来的属性会变，不能做身份主键；*Discovery* 是 OP 公布的元数据，含各端点与 `jwks_uri`。

*RP 会话*是应用自己的登录态（通常是 `HttpOnly` Cookie）；*OP 会话*是用户在身份平台的登录态。**两者独立**，这是登出问题反复出现的根源。

| 维度 | OAuth 2.0 | OIDC |
| --- | --- | --- |
| 解决的问题 | 授权委托：应用能代用户调用哪些接口 | 身份认证：这次登录的人是谁 |
| 主要产物 | access token（可能不透明）、refresh token | ID Token（JWT）+ access token |
| 令牌的受众 | 资源服务器 | 客户端自己 |
| 标准范围 | 自定义 scope | 必须含 `openid`，常用 `profile`、`email` |
| 身份标识 | 没有标准位置 | `sub` 声明 |
| 防重放机制 | `state`（防 CSRF） | `nonce`（防 ID Token 重放） |

ID Token 里每个字段都有明确用途，混着用就是事故的起点：

| 声明 | 含义 | 漏校验的后果 |
| --- | --- | --- |
| `iss` | 签发方标识 | 任何能签发 JWT 的服务都能冒充你的 OP |
| `aud` | 这个令牌发给谁 | 别处应用的令牌塞进你的回调也能登录成功 |
| `azp` | 多受众时的实际授权方 | 无法确认受众列表里哪个才是自己 |
| `exp` / `iat` | 有效期与签发时间 | 旧令牌可长期重放，会话永不过期 |
| `nonce` | 本次登录的一次性值 | 截获的旧 ID Token 可被重放成新会话 |
| `sub` | OP 内稳定的主体标识 | 用 `email` 关联会把人认错或并错账号 |
| `auth_time` / `acr` / `amr` | 实际认证时刻与方式 | “刚做过 MFA”这类分级要求形同虚设 |

## 工作原理

一次客服登录退款后台，按下面的顺序发生：

1. **准备登录**：RP 生成 `state` 与 `nonce`，连同 PKCE 的 `code_verifier` 存进一次性“登录前会话”，绑定本次浏览器。
2. **发起授权**：浏览器跳转到 OP 的授权端点，带 `response_type=code`、`client_id`、`redirect_uri`、`scope=openid profile email`、`state`、`nonce`、`code_challenge`。**`openid` 这个 scope 就是 OIDC 与纯 OAuth 的分界线**。
3. **OP 认证**：OP 检查自己的会话，未登录则要求密码与 OTP；已登录时可能直接确认授权，这正是“静默重新认证”的来源。
4. **回调**：OP 带 `code` 与 `state` 跳回 `redirect_uri`。RP 必须常数时间比对 `state`，不一致立即丢弃。
5. **换取令牌**：RP 在后端用 `code` + `code_verifier` + 客户端凭据换取 `id_token` 与 `access_token`，不能经过浏览器。
6. **校验 ID Token**：白名单确认 `alg` → 从 `jwks_uri` 取 `kid` 对应公钥验签 → 通过后才读声明，依次校验 `iss`、`aud`（必要时 `azp`）、`exp`/`iat`、`nonce`；有分级要求再比 `auth_time` 与 `acr`。
7. **关联账号**：以 `iss` + `sub` 为唯一键查本地账号，首次登录做显式关联并留痕。<u>不要用 `email` 自动合并账号</u>，邮箱可能未验证或被回收。
8. **建立 RP 会话**：签发 `HttpOnly; Secure; SameSite=Lax` Cookie，里面存 `sub`、`sid`、`auth_time` 与认证强度；access token 只留在后端调用资源。

退出流程是被忽视的一半：

1. **清本地**：删自己的会话 Cookie，这是唯一只靠自己就能保证生效的一步。
2. **通知 OP**：重定向到 `end_session_endpoint`，带 `id_token_hint` 与 `post_logout_redirect_uri`，让 OP 清掉**它自己的**会话。
3. **确认效果**：此后静默认证失败，用户必须重新输入凭据——共享电脑靠的就是这一步。
4. **通知其他应用**：OP 用*前端通道登出*（隐藏 iframe 加载各 RP 的 `frontchannel_logout_uri`，带 `iss` 与 `sid`）或*后端通道登出*（服务端直接向 `backchannel_logout_uri` POST 一个 `logout_token`）通知各 RP。
5. **按 `sid` 精确删除**：RP 按校验 ID Token 的规则校验 `logout_token`（签名、`iss`、`aud`、事件声明），再按 `sid` 删那一个会话，而不是把所有人一起踢下线。

后端通道不依赖浏览器，能覆盖“用户直接关掉页面”；前端通道在限制第三方 Cookie 的浏览器里可能加载失败，所以两者都支持、以后端通道为准。

## 架构与选型

| 方案 | 适用场景 | 不适用场景 | 主要代价 |
| --- | --- | --- | --- |
| OIDC 授权码 + PKCE | 员工或顾客的交互式登录，需要 MFA、SSO 与登录留痕 | 无人参与的机器对机器调用 | 需维护 Discovery 缓存、JWKS 轮换、回调与登出端点 |
| 纯 OAuth 2.0 + 自建用户表 | 已有账号体系，只要第三方 API 的调用授权 | 要复用企业目录、要单点登出 | 身份与授权两套真相，易放任 access token 当身份 |
| SAML 2.0 | 企业 IdP 只支持 SAML、集团统一 SSO | 新移动端与 SPA、IdP 已提供 OIDC | XML 签名与规范化问题难排查 |
| 自建用户名密码 | 内部小工具、无目录服务 | 顾客端、有合规审计要求的登录 | 密码库、MFA、找回、防撞库全部自己扛 |

选型按四个问题定序：谁是身份权威（已有目录就接过去）、退出要求多严（要“真正退出”必须走 OP 登出端点）、客户端类型（SPA 与移动端用授权码 + PKCE，或改用后端会话/BFF）、需要哪些属性（`group`、`role` 是否由 OP 提供）。**隐式流程**与**用 ID Token 当 API 凭据**都不推荐：前者把令牌放进 URL 片段，后者受众不对。

## 最小示例

问题：用 Python 标准库实现 RP 侧的 ID Token 校验，用八种输入检验它能否区分合法令牌与七类问题令牌。环境 Python 3.8+、仅标准库、不联网；输出每行一个决定。

```python
import base64, hashlib, hmac, json

NOW = 1_765_000_000          # 固定“当前时间”，让输出可复现
SKEW = 60                    # 容忍 60 秒时钟偏移，不宜再放大
ISSUER = "https://login.qingkong.example"   # 唯一可信签发方，必须精确匹配
CLIENT_ID = "refund-portal"                 # 本应用的 client_id，必须出现在 aud
SECRET = b"demo-only-shared-secret"         # 仅演示；生产用 OP 公钥验非对称签名
ALLOWED_ALGS = ("HS256",)                   # 生产通常只允许 RS256 或 ES256


def b64url(data: bytes) -> str:
    # JWT 各段使用 base64url 并去掉尾部填充，不能用标准 base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)   # 还原被去掉的 “=” 填充
    return base64.urlsafe_b64decode(segment + pad)


def sign(header: dict, payload: dict) -> str:
    # 扮演 OP 的签发端；真实 ID Token 由 OP 用私钥签名，RP 拿不到私钥
    h = b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    p = b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = hmac.new(SECRET, f"{h}.{p}".encode("ascii"), hashlib.sha256).digest()
    return f"{h}.{p}.{b64url(sig)}"


def verify_claims(claims: dict, expected_nonce: str, now: int) -> list:
    errs = []
    # iss 必须与配置值完全相等，任何“前缀匹配”都等于放行同域其他服务
    if claims.get("iss") != ISSUER:
        errs.append("iss_mismatch")
    aud = claims.get("aud")
    audiences = aud if isinstance(aud, list) else [aud]
    if CLIENT_ID not in audiences:
        errs.append("aud_mismatch")          # 令牌是发给别的应用的，不能收
    elif len(audiences) > 1 and claims.get("azp") != CLIENT_ID:
        errs.append("azp_mismatch")          # 多受众时必须确认“我是被授权方”
    if now > claims.get("exp", 0) + SKEW:    # 过期判断带偏移，方向不能写反
        errs.append("expired")
    if claims.get("iat", 0) > now + SKEW:
        errs.append("iat_in_future")         # 签发时间在未来，多半是时钟或伪造
    if not claims.get("sub"):
        errs.append("sub_missing")           # 没有稳定主体标识就建不了可信会话
    if claims.get("nonce") != expected_nonce:
        errs.append("nonce_mismatch")        # 防重放：必须比对登录时存下的值
    return errs


def verify(token: str, expected_nonce: str, now: int = NOW) -> list:
    header_seg, payload_seg, sig_seg = token.split(".")
    header = json.loads(b64url_decode(header_seg))
    # 先按白名单定算法，再决定怎么验：绝不让令牌头决定验证方式
    if header.get("alg") not in ALLOWED_ALGS:
        return ["alg_not_allowed"]
    expected = hmac.new(
        SECRET, f"{header_seg}.{payload_seg}".encode("ascii"), hashlib.sha256
    ).digest()
    try:
        got = b64url_decode(sig_seg)
    except Exception:
        return ["bad_signature"]
    if not hmac.compare_digest(expected, got):   # 常数时间比较，避免计时侧信道
        return ["bad_signature"]                 # 签名不过就返回，声明一律不读
    claims = json.loads(b64url_decode(payload_seg))
    return verify_claims(claims, expected_nonce, now) or ["ok"]


BASE = {
    "iss": ISSUER,
    "sub": "u_1001",            # 稳定的用户标识，账号关联用它而不是 email
    "aud": CLIENT_ID,
    "exp": NOW + 300,           # 令牌有效期 5 分钟
    "iat": NOW,
    "nonce": "n-8f3a",          # 发起授权请求时生成并存在用户会话里
    "auth_time": NOW - 30,      # 实际完成认证的时刻，供 max_age 判断
    "amr": ["pwd", "otp"],      # 认证方式，供分级授权判断
}
HS = {"alg": "HS256", "typ": "JWT", "kid": "k-2026-10"}

valid = sign(HS, BASE)
h, p, s = valid.split(".")
tampered = f"{h}.{b64url(json.dumps({**BASE, 'sub': 'u_9999'}, separators=(',', ':'), sort_keys=True).encode())}.{s}"
none_alg = f"{b64url(json.dumps({'alg': 'none', 'typ': 'JWT'}, separators=(',', ':')).encode())}.{p}."

cases = [
    ("valid", valid, "n-8f3a"),
    ("iss trailing slash", sign(HS, {**BASE, "iss": ISSUER + "/"}), "n-8f3a"),
    ("aud other client", sign(HS, {**BASE, "aud": "store-web"}), "n-8f3a"),
    ("multi aud no azp", sign(HS, {**BASE, "aud": [CLIENT_ID, "store-web"]}), "n-8f3a"),
    ("expired", sign(HS, {**BASE, "exp": NOW - 120}), "n-8f3a"),
    ("nonce mismatch", valid, "n-attacker"),
    ("alg none", none_alg, "n-8f3a"),
    ("payload tampered", tampered, "n-8f3a"),
]
for name, token, nonce in cases:
    print(f"{name:20} {','.join(verify(token, nonce))}")
```

运行 `python3 oidc_verify.py`，预期输出：

```text
valid                ok
iss trailing slash   iss_mismatch
aud other client     aud_mismatch
multi aud no azp     azp_mismatch
expired              expired
nonce mismatch       nonce_mismatch
alg none             alg_not_allowed
payload tampered     bad_signature
```

整体流程是：拆三段 → 拒绝算法 → 常数时间验签 → 才解析声明 → 逐项比对 → 全过才返回 `ok`。三个关键设计点：

- **算法白名单先于验签**。若像失败实现那样“读头里的 `alg` 再决定验证方式”，`none` 就变成跳过验签，`HS256` 还会被拿公钥当 HMAC 密钥，这就是算法混淆攻击。
- **签名失败立即返回**，不读任何声明，否则日志与账号关联会先被伪造的 `sub` 污染。
- **演示用 `HS256` 是为了离线可跑**。生产要换成 OP 公钥验 `RS256`/`ES256`，按 `kid` 缓存密钥，遇未知 `kid` 才刷新一次。

一个真实 ID Token 的载荷（示例报文，字段值为示意）：

```json
{
  "iss": "https://login.qingkong.example",
  "sub": "01HQ8Z3K7T9V2M4R6W8X0Y2A4B",
  "aud": "refund-portal",
  "exp": 1765000300,
  "iat": 1765000000,
  "nonce": "n-8f3a1c55",
  "auth_time": 1764999970,
  "amr": ["pwd", "otp"],
  "preferred_username": "li.wei"
}
```

## 动手实验

### 前置条件

本机有 `python3`（3.8+）和一个可写目录；不需要第三方库、网络或真实身份平台账号。

### 步骤

1. 把上面的代码保存为 `oidc_verify.py`，运行一次，对照“预期输出”逐行核对。
2. 把 `SKEW` 改为 `0` 再运行：`expired` 行仍是 `expired`，其余不变，说明偏移只用于容错。
3. 把 `ALLOWED_ALGS` 改为 `("HS256", "none")` 再运行：`alg none` 行变成 `bad_signature`。真正的 `none` 攻击发生在“按头里的算法决定是否验签”的实现里，这段代码没有那个分支。
4. 注释掉 `verify_claims` 中的 `nonce` 比对再运行：`nonce mismatch` 变成 `ok`，你刚亲手打开了一个重放窗口。
5. 增加 `auth_time` 校验：若 `now - claims.get("auth_time", 0) > 300` 则追加 `reauth_required`，并新增用例 `("stale auth_time", sign(HS, {**BASE, "auth_time": NOW - 600}), "n-8f3a")`。

### 预期结果

步骤 2 只有 `expired` 行受影响；步骤 3 中 `alg none` 变为 `bad_signature`，其余七行不变；步骤 4 中 `nonce mismatch` 变为 `ok`；步骤 5 新增用例输出 `reauth_required`，原八行不变。

### 验证方法

把预期结果写成断言，例如 `assert verify(valid, "n-attacker") == ["nonce_mismatch"]`；运行 `python3 -m unittest` 全绿即说明校验顺序与判定逻辑一致。再把 `CLIENT_ID` 改成别的值，确认 `valid` 行变为 `aud_mismatch`。

### 清理方法

删除 `oidc_verify.py` 与 `__pycache__`。实验只在内存里生成令牌，不访问 OP、不落数据库，没有远端资源需要回收。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 换了身份平台后，全部用户被认成同一个人 | 用 `email` 或第三方 `user_id` 当主键，字段语义变了 | 打印载荷的 `iss`/`sub` 与本地账号表主键对照 | 以 `iss` + `sub` 做唯一键，`email` 只做展示与辅助关联 |
| 验签直接失败 | JWKS 轮换后未刷新，或 `kid` 缓存过期 | 比对令牌头 `kid`/`alg` 与 `jwks_uri` 当前密钥集合 | 缓存 JWKS，遇未知 `kid` 刷新一次再判失败并告警 |
| 偶发“令牌过期”，重试又好了 | 容器时钟漂移，或把 `exp` 的秒当成毫秒 | 比对节点 NTP 时间与 `exp`、`iat` 的差值 | 同步 NTP，`SKEW` 控制在 60 秒内 |
| 点了退出，再点链接又直接进去了 | 只清了 RP 会话，没走 `end_session_endpoint` | 退出后查看 OP 域下会话 Cookie 是否仍存在 | 走 RP 发起登出，并启用后端通道登出兜底 |

## 安全与生产注意事项

**<u>把 ID Token 或 access token 放进 `localStorage` 并由前端脚本读取，等于把登录态交给任何一次 XSS。</u>** 一段第三方统计脚本就能读走令牌，攻击者可重放到过期为止，日志里看不出异常。缓解：会话放服务端、只发 `HttpOnly; Secure; SameSite=Lax` Cookie；SPA 用 BFF 保存令牌；有效期 5–15 分钟并配刷新令牌轮换。

**<u>`iss`、`aud`、`nonce` 任一不校验，攻击者就能把“发给别的应用的令牌”或“截获的旧令牌”塞回你的回调，直接登录成受害者。</u>** 漏 `aud` 时任何同 OP 应用的令牌都能登入你的系统；漏 `nonce` 时截获的登录可无限重放；漏 `iss` 时自建的测试 OP 也能签发可登录的令牌。缓解：算法白名单 + `jwks_uri` 验签 + 全量声明校验，`nonce` 一次性消费，登录前会话 TTL 不超过 10 分钟。

**<u>退出只清本地 Cookie，OP 会话仍在，共享电脑上的下一个人点一下“登录”就以你的身份进入退款后台。</u>** 对超过 500 元的退款审批而言，这等同于审批权被转交，审计只能看到受害者。缓解：RP 发起登出并携带 `id_token_hint`，启用后端通道登出按 `sid` 失效会话，并给高权限后台加空闲与绝对超时。`logout_token` 同样要验签，否则任何人 POST 一个假令牌就能把全部用户踢下线。

## 本课总结

- OAuth 2.0 管授权、OIDC 管认证；`openid` 这个 scope 就是分界，access token 不是身份。
- **ID Token 是写给客户端自己看的证明信**，受众是 RP，不能拿去当资源服务器的访问凭据。
- 校验顺序固定为：算法白名单 → 验签 → `iss` → `aud`/`azp` → `exp`/`iat` → `nonce` →（按需）`auth_time`/`acr`。
- 账号关联用 `iss` + `sub`；`email` 只用于展示与已验证情况下的辅助。
- 退出要清两个会话：RP 会话靠本地删除，OP 会话靠 `end_session_endpoint`，多应用再靠后端通道登出按 `sid` 同步。

## 思考题

晴空商城要把客服后台与仓储看板接到同一个身份平台，并要求“客服在身份平台退出后，两个后台必须在 30 秒内失去登录态，顾客端不受影响”。请说明需要哪些 OP 能力、各 RP 要保存什么状态、后端通道登出如何“精确到会话而不误伤他人”，以及用什么证据证明 30 秒达成。

参考思路：需要 OP 支持 Discovery、`sid` 声明与后端通道登出；两个后台各保存 `sid` 到本地会话的映射，实现 `backchannel_logout_uri` 的验签与按 `sid` 删除；顾客端不注册该端点，成为独立信任域。证据包括 OP 投递日志、RP 登出耗时与失败率、一条自动化用例（退出后 5 秒与 30 秒各访问一次后台）加告警阈值。

## 小测

1. 下面哪一项是 OIDC 相对 OAuth 2.0 新增的产物？（多选）  
   A. `openid` 范围　B. ID Token　C. refresh token　D. Discovery 文档
2. 判断：资源服务器可以用 ID Token 校验调用者身份，因为它也是 OP 签名的 JWT。
3. 校验 ID Token 时，为什么必须先确认 `alg` 并验签，再去读 `sub` 和 `email`？
4. 用户在一个 RP 上点了退出，但再次访问时自动登录了。最可能漏掉的是哪一步？
5. 判断：`nonce` 的作用与 `state` 相同，都是防 CSRF。
6. 场景题：主管要求“审批 500 元以上退款时，必须确认客服最近五分钟内做过 MFA”。团队打算在退款接口里读 ID Token 的 `amr` 判断。这个设计有什么问题？你会怎么改？

## 答案与解析

1. **A、B、D。** `openid` 是进入 OIDC 的开关，ID Token 是认证结果，Discovery 让 RP 发现端点与 `jwks_uri`。C 的 refresh token 属于 OAuth 2.0，OIDC 只是复用。
2. **错。** ID Token 的 `aud` 是客户端自己，交给资源服务器等于错用受众；下游一多，身份断言还会扩散到不该持有它的地方。<u>资源服务器应校验 access token 或专用身份断言令牌。</u>
3. 因为声明本身未经保护，`email`、`sub` 都可随意填写，只有签名通过后才具备“OP 说过这话”的含义。先读声明再验签会把伪造身份写进日志与账号关联表，之后即使拒绝也已污染数据。
4. 漏掉了通知 OP 清自己的会话（`end_session_endpoint`）。RP 只删了自己的 Cookie，OP 会话仍在，下一次静默认证立刻重新签发 ID Token。<u>“点了退出”不等于“登出了身份平台”。</u>
5. **错。** `state` 绑定的是一次授权请求，防止别人把你的回调当成自己的回调（CSRF）；`nonce` 绑定 ID Token 与那次登录，防止旧令牌被重放。两者都一次性，但防的攻击不同。
6. 问题有三层：退款服务不是该 ID Token 的受众，读它属越界使用；ID Token 可能早已过期或被前端持有，证明不了“此刻”的认证强度；`amr` 只说用过哪些因素，`auth_time` 才说什么时候。改法：登录时把这两项写进服务端会话，审批时读会话，并用 `max_age` 触发重新认证。

### 动手实验参考

步骤 2 说明时钟偏移只影响“刚好过期”的边界，不能掩盖严重的时钟漂移；步骤 3 揭示算法白名单的意义在于**取消攻击者的选择权**，实现不再根据令牌头分支时，`none` 只是签名不符的废令牌；步骤 4 最值得警惕：删掉一行 `nonce` 比对，其余校验全部正常，截获的旧令牌仍能建立新会话；步骤 5 要用 `auth_time` 而不是 `iat`，因为令牌可能被重新签发。

## 延伸阅读与下一课

- OpenID Connect Core 1.0 规范：<https://openid.net/specs/openid-connect-core-1_0.html>，ID Token 的必需声明、校验规则与 UserInfo 定义以此为准。
- OpenID Connect Discovery 1.0：<https://openid.net/specs/openid-connect-discovery-1_0.html>，说明 `/.well-known/openid-configuration` 与 `jwks_uri`。
- OpenID Connect RP-Initiated Logout 1.0：<https://openid.net/specs/openid-connect-rpinitiated-1_0.html>，`end_session_endpoint` 的参数与 `id_token_hint` 用法。
- OpenID Connect Back-Channel Logout 1.0：<https://openid.net/specs/openid-connect-backchannel-1_0.html>，`logout_token` 的校验与 `sid` 语义。
- OAuth 2.0 授权框架（RFC 6749）：<https://www.rfc-editor.org/rfc/rfc6749>，本课始终假设的授权码流程基础。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[OAuth 2.0 授权流程与 PKCE](04-oauth2-flows-and-pkce.md)。
- 下一课：[SSO、SAML 与企业身份接入](06-sso-saml-and-enterprise-identity.md)。
