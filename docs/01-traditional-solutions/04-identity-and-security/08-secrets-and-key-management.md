---
title: Secret、证书与密钥管理
slug: secrets-and-key-management
module: traditional-solutions
stage: operate-and-optimize
type: core
difficulty: intermediate
duration: 50m
prerequisites:
  - rbac-abac-and-multi-tenant-permissions
outcomes:
  - 区分 Secret、密钥与证书三类资产的存放位置、有效期与失效方式
  - 用密钥层次和信封加密解释主密钥与数据密钥的分工
  - 设计一次带双版本宽限期的轮换，并以旧值被拒绝作为完成标准
  - 写出泄露处置的顺序，说明为什么止血先于追查
last_reviewed: 2026-10-19
---

# Secret、证书与密钥管理

## 为什么需要学习

晴空商城的退款服务要同时握住几样不能见光的东西：支付商 API 私钥、订单库密码、Webhook 验签密钥、TLS 证书。它们不能写进代码，却必须在凌晨无人值守时被程序自动拿到。

上个月促销当天证书在 23:40 到期，支付商回调全部握手失败，退款积压到次日。排查又发现 CI 变量里的数据库密码三年没换，还被 `echo` 进了构建日志；值班同事第一反应是删日志，证据也没了。

> **核心结论：** Secret 管理的目标不是“把字符串藏好”，而是让每份凭据都有明确所有者、可追踪的取用路径，以及分钟级作废的能力。

## 学习目标

完成本课后，你能够：

- 区分 Secret、密钥与证书，说明各自存放位置、有效期与失效方式。
- 用密钥层次与信封加密解释主密钥为何不必下发。
- 设计带双版本宽限期的轮换，用审计证明旧值已失效。
- 对一段日志或仓库内容给出泄露判定与处置顺序，说明每一步的先后理由。

## 前置知识

- 回看上一课：[RBAC、ABAC 与多租户权限](07-rbac-abac-and-multi-tenant-permissions.md)。
- 知道环境变量与配置文件的作用，能说清应用读到的值来自哪里。
- 知道 TLS 用服务端证书证明域名身份，客户端校验证书链。
- 了解最小权限与职责分离的基本含义。

## 业务场景

退款服务上线前的安全评审要求运维讲清“这个服务依赖哪些秘密”：

- **支付商 API 私钥**：签名退款请求，一年一换；泄露等于任何人能替商城发起退款。
- **订单库密码**：读写 `orders` 库，轮换要重启连接池。
- **Webhook 验签密钥**：与支付商共享的 HMAC 密钥，两侧必须同时更换。
- **TLS 证书与私钥**：`refund-api.qingkong.example`，90 天到期。
- **CI 部署令牌**：能往生产命名空间推镜像，权限压到最小。

评审追问：这些值存在哪、谁能读？换一份要多久、要停机吗？有人把带 Key 的日志贴到公开仓库，第一步做什么？

## 核心概念

*Secret*（秘密材料）是需要保密才能维持效力的数据：密码、API Key、私钥、连接串。它与*配置*的区别不在格式而在泄露后果：配置泄露最多暴露行为，Secret 泄露直接交出权限。

*密钥层次*（key hierarchy）把密钥分层，避免一把钥匙开所有门：最上层是*主密钥*（master key，常驻 KMS 或 HSM，不以明文离开硬件），中间是*数据密钥*（data key，每条密文独立）。用主密钥加密数据密钥、再用它加密内容，叫*信封加密*（envelope encryption）：主密钥调用次数少，一条数据密钥泄露只影响对应数据。

*KMS*（Key Management Service）托管主密钥与加解密接口；*Vault* 一类*秘密管理器*（secrets manager）能签发*动态凭据*（dynamic credentials）——每次申请得到一个几小时后自动过期的数据库账号。

*证书*（X.509 certificate）把公钥与域名绑定并由*CA*（证书颁发机构）签名，服务器持有对应*私钥*，握手时证明自己。它到期即失效；私钥泄露后必须*吊销*（revocation），并经 CRL 或 OCSP 告知客户端。

*轮换*（rotation）是用新值替换旧值的过程，<u>只有旧值真的失效，轮换才算完成</u>。*注入*（injection）是把 Secret 交给进程的方式：环境变量、挂载文件、按需拉取或 SDK 解密。

| 资产 | 谁签发 | 典型有效期 | 失效方式 | 泄露后果 |
| --- | --- | --- | --- | --- |
| 订单库密码 | 自己或 DBA | 90 天 | 改密码并重启连接池 | 直读订单与地址 |
| 支付商私钥 | 支付商 | 1 年 | 支付商后台作废 | 可伪造退款请求 |
| Webhook 验签密钥 | 双方协商 | 180 天 | 双写窗口后停旧钥 | 可伪造回调 |
| TLS 证书 | 公共 CA | 90 天 | 到期或吊销 | 可被冒充劫持 |
| CI 部署令牌 | 平台 | 30 天 | 平台侧吊销 | 可推恶意镜像 |

## 工作原理

**存储与注入**

1. 主密钥只存在 KMS 或 HSM；写入时生成数据密钥加密明文，再用主密钥封装这份数据密钥，把密文、*封装结果*、*指纹*和元数据一起入库。
2. 应用不保存管理员令牌，而用工作负载身份（ServiceAccount、云实例角色）换一个几分钟有效的*短期令牌*。
3. 启动时凭短期令牌只拉本服务被授权的路径，拒绝“一次拉全量”。
4. 值注入内存或权限 `0400` 的临时文件，不写进镜像层和持久卷；日志输出前脱敏，只留前缀与指纹，每次读取写审计。

**轮换**

1. 生成新值登记为新版本，旧版本标记为“已弃用但宽限期内仍可验证”。
2. 把新值发布到使用方：更新挂载文件、重发环境变量，或让应用重新拉取。
3. 用审计中的新旧版本调用比例确认切换完成，而不是靠人汇报。
4. 宽限期（按最长重启周期定）结束后吊销旧版本，确认旧值请求被拒绝，并把下次到期时间交给监控。

**证书签发与续期**

1. 客户端提交域名并完成所有权挑战（HTTP-01 或 DNS-01），CA 验证后签发证书与链。
2. 私钥在本地生成、绝不上传；部署时确保链完整（含中间证书）并启用 OCSP stapling。
3. 到期前 30 天自动续期，成功后必须让进程重载证书。
4. 私钥泄露时先吊销再签发新证书，吊销比删文件更关键。

**泄露处置**

1. 确认：用指纹判断泄露的是哪个版本，别为早已作废的值开会。
2. 止血：立刻吊销或作废，别在“先查清楚”上耽误——攻击者可能已复制。
3. 换新：签发新版本，按轮换流程发布。
4. 查影响面并保全证据：拉读取审计、云审计与出网记录，日志先归档再清理。
5. 复盘：它为什么能进日志或仓库？补扫描与脱敏，而不是只写检讨。

## 架构与选型

| 方案 | 适用场景 | 不适用或代价 |
| --- | --- | --- |
| `.env` 与本地配置文件 | 单人原型、离线教学 | 值会进备份与 shell history，多环境必然泄漏 |
| CI/CD 的 Secret 变量 | 构建期注入令牌 | 不适合运行期长期凭据；回显会写进日志 |
| Kubernetes Secret | 集群内给应用注入 | <u>默认只做 base64 编码</u>，未配静态加密时等同盟文，必须配 RBAC 与 etcd 加密 |
| 云 Secrets Manager | 需要托管审计与自动轮换 | 账号与区域绑定，迁移成本高 |
| Vault 类秘密管理器 | 多团队共用、动态短期凭据 | 自身成为关键依赖，要解决高可用与解封 |
| KMS 信封加密、HSM | 密文存库、根密钥与签名 | 前者怕高频读取；后者成本高、密钥不可导出 |

选型归结为四个问题：谁需要读、能否即时吊销、换一次要多久、是否要求密钥不出硬件。

**越难吊销的凭据，越应该只给最小权限和最短有效期。**

## 最小示例

问题：用标准库验证三件事——信封加密可还原且同一明文两次密文不同、改动能被检测、轮换时旧值宽限期内可用而之后被拒。环境为 Python 3.9+，不联网、不写文件。

<u>下面的密钥流用 HMAC-SHA256 计数器模式拼出，只为让流程可观察；生产请用 AES-GCM 或云 KMS 的封装接口，不要自己实现密码学。</u>

```python
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

def keystream(key: bytes, label: bytes, nonce: bytes, length: int) -> bytes:
    # label 区分两种用途，避免同一密钥流在两处复用
    out, counter = [], 0
    for _ in range((length + 31) // 32):
        out.append(hmac.new(key, label + nonce + counter.to_bytes(8, "big"),
                            hashlib.sha256).digest())
        counter += 1
    return b"".join(out)[:length]

def xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))

def seal(master_key: bytes, plaintext: bytes) -> dict:
    data_key = secrets.token_bytes(32)     # 每条密文一份数据密钥，缩小爆炸半径
    nonce = secrets.token_bytes(12)        # 一次性随机数，让同一明文两次密文不同
    body = xor(plaintext, keystream(data_key, b"data", nonce, len(plaintext)))
    # 加密不防篡改：用数据密钥算标签，一位变化就能发现
    tag = hmac.new(data_key, b"tag" + nonce + body, hashlib.sha256).digest()[:16]
    # 数据密钥由主密钥封装后随密文存，主密钥不必下发
    wrapped = xor(data_key, keystream(master_key, b"wrap", nonce, 32))
    return {"nonce": nonce, "wrapped_key": wrapped, "ciphertext": body, "tag": tag}

class Tampered(Exception):
    pass

def open_sealed(master_key: bytes, env: dict) -> bytes:
    nonce, body = env["nonce"], env["ciphertext"]
    data_key = xor(env["wrapped_key"], keystream(master_key, b"wrap", nonce, 32))
    expect = hmac.new(data_key, b"tag" + nonce + body, hashlib.sha256).digest()[:16]
    if not hmac.compare_digest(expect, env["tag"]):   # 常量时间比较，避免侧信道
        raise Tampered("密文或标签被改动")
    return xor(body, keystream(data_key, b"data", nonce, len(body)))

MASTER = secrets.token_bytes(32)          # 生产中由 KMS 持有，应用只见封装结果
plain = b"pg://refund:Pa55w0rd@orders-db:5432/orders"   # 教学用假值，禁止写真实凭据
e1, e2 = seal(MASTER, plain), seal(MASTER, plain)
print("解密还原:", open_sealed(MASTER, e1) == plain)
print("同一明文两次密文相同:", e1["ciphertext"] == e2["ciphertext"])
bad = dict(e1, ciphertext=e1["ciphertext"][:-1] + bytes([e1["ciphertext"][-1] ^ 0x01]))
try:
    open_sealed(MASTER, bad)
except Tampered:
    print("篡改检测: 抛出 Tampered")

def fingerprint(value: str) -> str:
    # 只存指纹：拖库也还原不出，但能比对是否同一份
    return hashlib.sha256(value.encode()).hexdigest()[:12]

@dataclass
class SecretVersion:
    version: int
    fingerprint: str
    status: str
    reject_after: datetime   # 该版本失效时间，降级时收紧为宽限期

@dataclass
class ManagedSecret:
    name: str
    versions: list = field(default_factory=list)

def rotate(secret: ManagedSecret, now: datetime, grace=timedelta(hours=72)) -> str:
    for v in secret.versions:
        if v.status == "active":
            v.status = "deprecated"
            v.reject_after = now + grace      # 给使用方留切换窗口，不是立刻删
    raw = "sk_" + secrets.token_urlsafe(24)
    latest = max((v.version for v in secret.versions), default=0) + 1
    secret.versions.insert(0, SecretVersion(latest, fingerprint(raw), "active",
                                            now + timedelta(days=90)))
    return raw

def accepts(secret: ManagedSecret, presented: str, now: datetime) -> tuple:
    fp = fingerprint(presented)
    for v in secret.versions:
        if v.fingerprint != fp:
            continue
        if v.status == "active":
            return True, v.version
        if v.status == "deprecated" and now < v.reject_after:
            return True, v.version
        return False, v.version
    return False, None

T0 = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
db = ManagedSecret("refund/orders-db-password")
old = rotate(db, T0 - timedelta(days=89))   # 89 天前发的旧值
new = rotate(db, T0)                        # 今天轮换：旧值进入 72 小时宽限
print("新值可用:", accepts(db, new, T0))
print("宽限期内旧值可用:", accepts(db, old, T0)[0])
print("宽限期后旧值仍可用:", accepts(db, old, T0 + timedelta(hours=73))[0])
print("版本数与指纹:", len(db.versions), db.versions[0].fingerprint)

LEAKS = re.compile(r"(sk_[A-Za-z0-9_\-]{8,}|-----BEGIN [A-Z ]+PRIVATE KEY-----)")

def redact(text: str) -> str:
    # 保留前三位便于定位哪个 Key，其余全部抹掉
    return LEAKS.sub(lambda m: m.group(1)[:3] + "<REDACTED>", text)

line = "call failed key=sk_live_9fQ2mZx7Lp0aTaR4 host=pp.example.com"
print("脱敏后:", redact(line))
print("仍含原始 Key:", "sk_live_9fQ2mZx7Lp0aTaR4" in redact(line))
```

把代码存为 `secret_demo.py`，运行 `python3 secret_demo.py` 的预期输出（指纹与随机部分随机器不同）：

```text
解密还原: True
同一明文两次密文相同: False
篡改检测: 抛出 Tampered
新值可用: (True, 2)
宽限期内旧值可用: True
宽限期后旧值仍可用: False
版本数与指纹: 2 a28b02f775d8
脱敏后: call failed key=sk_<REDACTED> host=pp.example.com
仍含原始 Key: False
```

两处设计值得记住：标签是必需品，<u>只加密不认证会让攻击者翻位篡改密文</u>；轮换用“指纹 + 状态 + 拒绝时间”表达，才能不停服也证明旧值失效。

## 动手实验

### 任务：秘密清单、轮换演练与泄露处置

前置条件：Python 3.9+，最小示例已跑通；不需要云账号或联网。

1. 填全下表，标准是每一行都能指出一个具体负责人。

| 资产 | 所有者 | 存放位置 | 有效期 | 读取方 |
| --- | --- | --- | --- | --- |
| 支付商 API 私钥 |  |  |  |  |
| 订单库密码 |  |  |  |  |
| Webhook 验签密钥 |  |  |  |  |
| TLS 证书与私钥 |  |  |  |  |
| CI 部署令牌 |  |  |  |  |

2. 用 `rotate` 与 `accepts` 连续做两次轮换，观察轮换当天、宽限期内、宽限期后三个时间点。
3. 把宽限期改成 1 小时重跑，记录哪一行结果变化，并写出它对应现实中的哪种故障。
4. 造一条带完整 Key 的日志用 `redact` 处理，再换成恒等函数，确认“原始 Key 仍在”的断言失败。
5. 列出吊销顺序：确认版本、吊销、发布新值、查审计、归档证据、复盘，标注每步谁执行、谁验收。

预期结果：清单每行有具体所有者；旧值宽限期内通过、之后被拒；1 小时宽限期下旧值在重启周期内被拒。

验证方法：`accepts` 的返回值与版本号能和审计对上；`redact` 后用原始 Key 检索必须为 `False`。

清理方法：删除临时脚本即可；<u>曾把示例假值换成真实凭据的，立即轮换那份凭据</u>。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 证书续期后浏览器仍报过期 | 进程还握着旧文件句柄，未重载 | `openssl s_client -connect host:443 \| openssl x509 -noout -dates` 对比部署文件 | 续期后触发 reload，并对真实握手做外部探测 |
| 日志里出现完整 Key | 中间件打印请求头，或堆栈带连接串 | 按前缀在日志平台检索 | 采集端脱敏，只留指纹，并轮换泄露值 |
| 轮换后部分请求 401 | 使用方未取到新版本，或宽限期过短 | 看审计里新旧版本调用比例 | 先发布新值再停旧值，宽限期覆盖重启周期 |
| 以为 Kubernetes Secret 是加密的 | 默认只做 base64 编码 | 用 `kubectl get secret -o yaml` 解一下 | 启用 etcd 静态加密与 RBAC，值放外部 KMS |
| 镜像里翻出数据库密码 | 构建时 `COPY` 了 `.env` 或写进 `ENV` | `docker history` 与解包镜像层 | 运行时注入，重建镜像，轮换密码 |

## 安全与生产注意事项

**<u>把 Secret 当配置文件提交进仓库或构建进镜像，等于永久公开。</u>** Git 历史、镜像层、CI 缓存和他人的 fork 都长期留副本，删掉当前文件不会让值消失。缓解：只做运行时注入，提交钩子与 CI 里跑密钥扫描，发现即轮换。

**<u>只轮换不吊销，或先排查后止血，会把泄露窗口从分钟级拖成数周。</u>** 攻击者拿到值后常静默使用，不触发告警；旧版本还能验证，泄露就一直有效。缓解：验收标准写成“旧值请求被拒绝”，处置第一步是吊销并归档审计日志。

**<u>证书续期成功但没重载进程，会把一次自动续期变成一次凌晨事故。</u>** 内存里的证书不会随磁盘文件更新，监控又常只看“续期任务成功”。缓解：续期即触发 reload，并探测外部可用性。

## 本课总结

- Secret、密钥与证书是三类资产，有效期与失效方式都不同。
- 密钥分层缩小爆炸半径：主密钥留 KMS/HSM，数据密钥随密文走。
- 轮换的完成标准是旧值被拒绝，宽限期要覆盖最长重启周期。
- 泄露处置顺序是“确认—吊销—换新—查影响面—保全证据—复盘”，止血先于追查；证书的两个盲点是链是否完整、进程是否真用上了新文件。

## 思考题

晴空商城要把退款服务拆成三个微服务，安全团队要求“每个服务只能读自己的 Secret”。请说明你会怎样划分命名空间与访问策略；并分析支付商私钥必须被两个服务共用时，共享一份、拆成两份、引入签名代理三种做法各自的代价。

参考思路：优先不共享——签名代理把私钥限制在单一服务，其他服务请求它签名，代价是多一次网络跳转和新的可用性依赖。拆成两份需支付商支持多密钥，能独立轮换与吊销，代价是配置与对账变复杂。共享一份最省事，但任何一方泄露都波及所有方。评价标准：是否说清爆炸半径、轮换影响面与审计粒度。

## 小测

1. Kubernetes Secret 默认在 etcd 中加密存储，对还是错？
2. 下列哪一项最需要“先吊销、后排查”？  
   A. 还有 80 天到期的证书　B. 已贴在公开仓库日志里的支付商私钥　C. 上季度作废的测试 Key　D. 只在内存里出现过的令牌
3. 信封加密为什么每条密文要配独立的数据密钥？
4. 判断一次轮换是否完成，应该看什么证据？
5. 场景题：值班同学发现日志里有完整数据库连接串，打算先删日志再改密码。你同意吗？

## 答案与解析

1. **错。** 默认只做 base64 编码，能直接解出明文；静态加密须配置 `EncryptionConfiguration` 并收紧 RBAC，更高要求放外部 KMS。
2. **B。** 已确认泄露且当前仍有效，多一秒都能被使用。A 尚未泄露，应安排续期；C 已作废，只需确认没有衍生凭据；D 未离开进程内存，先确认是否写进日志。
3. 一条数据密钥泄露只影响对应密文，同时减少主密钥调用与延迟。若全部密文共用一个数据密钥，一次泄露就波及全部。
4. 看审计里旧版本调用比例归零、旧值请求被拒。“新值已发布”只是动作，失效才是结果。
5. 不同意。删日志先销毁证据，无法判断泄露范围与哪份凭据该作废。顺序：归档日志、吊销该账号、换新密码并发布、依据审计追查影响面，最后补脱敏与扫描。

### 动手实验参考

宽限期改短后，“宽限期内旧值可用”从 `True` 变成 `False`，对应滚动发布没跑完、旧实例仍用旧值的间歇性 401。正确处理是让宽限期覆盖最长重启与回滚时间。分工：值班人吊销（分钟）、平台发布（小时）、安全查审计并归档（当天）、负责人复盘（一周）。

## 延伸阅读与下一课

- [NIST SP 800-57 Part 1 Rev. 5：密钥管理指南](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final)，密钥生命周期定义。
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)，存储与轮换实践清单。
- [RFC 8555：ACME 协议](https://www.rfc-editor.org/rfc/rfc8555)，签发与续期自动化的标准。
- [Kubernetes 文档：Secrets 的良好实践](https://kubernetes.io/docs/concepts/security/secrets-good-practices/)，base64 与静态加密边界。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[RBAC、ABAC 与多租户权限](07-rbac-abac-and-multi-tenant-permissions.md)。
- 下一课：[常见 Web/API 攻击与安全设计](09-web-api-attacks-and-secure-design.md)。
