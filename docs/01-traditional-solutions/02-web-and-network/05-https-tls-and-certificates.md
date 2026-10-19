---
title: HTTPS、TLS 与证书
slug: https-tls-and-certificates
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 55m
prerequisites:
  - headers-cookies-and-caching
outcomes:
  - 解释 TLS 握手中身份验证、密钥协商与加密传输各自解决的问题
  - 依据证书链、有效期、SAN 与用途判断一个 HTTPS 端点为何被客户端拒绝
  - 列出 HTTPS 上线检查清单，说明 TLS 终止位置、私钥管理与证书续期的处理方式
last_reviewed: 2026-10-19
---

# HTTPS、TLS 与证书

## 为什么需要学习

晴空商城的对外入口各自出过事：顾客登录的 Cookie 在明文 HTTP 下能被同一网络里的中间人读取；支付方回调因证书过期中断三小时；客服后台的图片仍是 `http://`，被浏览器当作混合内容拦截。开发同学的第一反应常是"加个锁、点掉警告"，代价却是把整条链路退化成可以被任意替换的明文通道。

> **核心结论：** HTTPS 不是给页面加一把装饰性的锁，而是用证书证明"我连上的确实是 `api.qingkong.example`"，再用握手协商出的会话密钥保护这段通信的机密性与完整性。

## 学习目标

完成本课后，你能够：

- 用一句话说明 TLS 握手完成的三件事：*身份验证*、*密钥协商*、*加密传输*。
- 按"链、有效期、域名、用途"四步判断一张证书为什么被客户端拒绝。
- 运行最小验证脚本，区分"信任锚缺失"与"主机名不匹配"两类失败。
- 列出 HTTPS 上线检查清单，说明 TLS 终止位置与证书续期的落点。

## 前置知识

- 回看上一课：[Header、Cookie 与缓存](04-headers-cookies-and-caching.md)。
- 能读懂一次 HTTP 请求与响应：方法、状态码、Header 各自的作用。
- 知道域名经 DNS 解析成 IP，TCP 在 IP 之上建立连接。
- 不要求密码学或 OpenSSL 经验，命令都会给出并解释。

## 业务场景

晴空商城有四个对外入口，它们对 TLS 的要求并不相同：

- `shop.qingkong.example` 走 CDN，证书由 CDN 供应商托管。
- 支付方回调 `https://api.qingkong.example/pay/notify` 要求源站能独立接受公网 HTTPS 请求。
- 客服后台 `admin.qingkong.example` 由外包团队维护，员工在家办公后不再有内网边界。
- 仓库 WMS 的 `wms.qingkong.example` 接口里带收件人地址和电话。

约束具体到可检查：支付方合同要求 TLS 1.2 及以上、不接受自签证书；证书由谁续期、过期后谁先知道，都没写进 Runbook；去年一次过期让支付回调中断 3 小时，退款积压 400 单。

架构师要回答的不是"要不要 HTTPS"，而是 TLS 在哪一层终止、证书由谁续期、临期时靠什么信号在 5 分钟内发现。

## 核心概念

| 概念 | 本课程中的含义 | 晴空商城示例 |
| --- | --- | --- |
| *TLS* | 在 TCP 之上提供机密性、完整性和身份认证的协议 | 所有 `https://` 入口的底层协议 |
| *HTTPS* | 把 HTTP 报文放进 TLS 连接里传输，默认端口 443 | `shop.qingkong.example` |
| *证书* | CA 签名的 X.509 文件，把域名和公钥绑定在一起 | `api.qingkong.example` 的叶证书 |
| *CA* | 证书颁发机构，验证申请者身份并用私钥签发证书 | 支付方只接受公共 CA 签发的证书 |
| *证书链* | 叶证书 → 中间证书 → 根证书的签名序列 | 漏发中间证书时的典型故障 |
| *信任库* | 操作系统或运行时预置的可信根证书集合 | 运维电脑与容器镜像各有一套 |
| *SAN* | 主体备用名称，列出证书有效的域名或 IP | 证书里必须含 `api.qingkong.example` |
| *私钥* | 只留在服务端或密钥服务里，用于握手签名 | 泄露即代表站点身份可被冒用 |
| *HSTS* | 让浏览器今后只走 HTTPS 的响应头 | 防止回落到 `http://` |

两类加密的成本和职责完全不同：

| 维度 | 对称加密 | 非对称加密 |
| --- | --- | --- |
| 密钥 | 双方共享同一把密钥 | 公钥与私钥成对，公钥可公开 |
| 速度 | 快，适合大数据量 | 慢，计算开销高 |
| 主要职责 | 保护传输内容 | 身份验证与密钥协商 |
| 在 TLS 中的位置 | 加密握手后的应用数据 | 证书签名、握手阶段的密钥交换 |

有两处极易记反：<u>证书里只有公钥，私钥永远不应该出现在证书里，也不应该下发给客户端</u>；<u>浏览器信任的是签名链能否走到本地信任库，而不是域名看起来像不像官网</u>。

## 工作原理

### 握手：一次往返里完成三件事

以 TLS 1.3 为例：

1. 建立 TCP 连接后，客户端发送 `ClientHello`：支持的版本与套件、*SNI*（声明要访问的域名）、随机数，以及临时 ECDHE 公钥（`key_share`）。
2. 服务端回 `ServerHello`：选定版本与套件，并给出自己的临时 ECDHE 公钥。
3. 双方各自算出同一份共享秘密，派生出本次会话的对称密钥。
4. 服务端在已加密通道里发送 `Certificate`、`CertificateVerify`（用私钥签名握手记录）和 `Finished`。
5. 客户端验证证书链与签名，核对 `Finished` 后发送自己的 `Finished`。
6. 握手结束，之后每个 HTTP 报文都用对称密钥加密并附带完整性校验。

> **核心结论：** 证书和私钥只在握手阶段用于证明身份和签名，真正加密应用数据的是双方临时协商出来的对称密钥。

### 校验：客户端按五步否决一张证书

1. **建链**：从叶证书沿"签发者"向上追溯，直到命中本地信任库里的根证书。
2. **验签**：逐级用上级公钥验证下级证书签名，任何一环断裂都不可信。
3. **查有效期**：要求 `notBefore ≤ 当前时间 ≤ notAfter`，双方时钟必须准。
4. **查域名与用途**：主机名必须出现在 SAN 中，且扩展密钥用途（EKU）允许 `serverAuth`。
5. **查吊销**：通过 CRL、OCSP 或浏览器内置的撤销数据确认未被提前作废。

任何一步失败，握手都在 HTTP 之前终止，所以"接口 502、页面白屏"可能连一个字节的应用请求都没发出去。TLS 1.3 把流程压到 1-RTT 且证书加密后发送，1.2 需要 2-RTT、证书明文可见，但校验逻辑一致。

## 架构与选型

先判断这个入口是否真的需要 HTTPS：

| 场景 | 是否适用 | 依据 |
| --- | --- | --- |
| 公网 Web 页面与 API | 必须 | 网络路径不可信，且涉及 Cookie 与业务数据 |
| 内部服务间调用 | 建议 | 内网不等于可信，横向移动很常见 |
| 本地开发与自动化测试 | 可用自签证书 | 手动信任即可，不必申请公共证书 |
| 离线批处理与本机脚本 | 不适用 | 没有网络路径，也没有传输机密性需求 |

TLS 在哪一层终止，决定了证书装在哪里、谁能看到明文：

| 方案 | 优点 | 代价 | 典型适用 |
| --- | --- | --- | --- |
| CDN 或负载均衡终止 | 证书集中托管，卸载加密开销 | 供应商到源站之间可能是明文 | 静态资源、公开 API |
| 端到端重新加密 | 源站也走 TLS，链路全程加密 | 需维护两套证书与两段告警 | 支付回调、客服后台 |
| TCP 直通（不终止） | 密码学边界最完整 | 无法按路径做 WAF 和缓存 | 强合规或特殊协议 |

证书类型直接影响运维成本：

| 类型 | 覆盖范围 | 代价 | 适用场景 |
| --- | --- | --- | --- |
| 多域名（SAN） | 一张证书列多个域名 | 增删域名需重签 | 域名少且稳定 |
| 通配符 | 一级子域全覆盖 | 暴露面变大 | 结构固定的多子域 |

选型依据是三个问题：谁能看到明文、证书由谁续期、失效时靠什么发现。

## 最小示例

环境要求：`python3.8+` 与 `openssl`，全程离线。示例要把"证书被拒绝"变成一条可对照的错误码，而不是浏览器里一句模糊的警告。

第一步，生成一张只对 `localhost` 有效的自签证书：

```bash
openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout key.pem -out cert.pem -days 1 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
```

`-nodes` 让私钥不加密，便于脚本加载；`-days 1` 便于复现过期故障；`-addext` 写入 SAN，因为现代客户端只看 SAN。

第二步，查看证书的关键字段：

```bash
openssl x509 -in cert.pem -noout -subject -dates -ext subjectAltName
```

预期输出（日期随生成时间变化）：

```text
subject=CN=localhost
notBefore=Oct 19 08:29:24 2026 GMT
notAfter=Oct 20 08:29:24 2026 GMT
X509v3 Subject Alternative Name:
    DNS:localhost, IP Address:127.0.0.1
```

第三步，启动本地 TLS 服务端并做三次连接测试：

```python
import socket
import ssl
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

CERT, KEY = "cert.pem", "key.pem"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass  # 关掉请求日志，让输出只剩握手结果


class QuietServer(HTTPServer):
    def handle_error(self, request, client_address):
        pass  # 客户端只握手就断开，忽略服务端读取异常


# 1. 服务端上下文装载私钥与证书；低于 TLS 1.2 的握手直接拒绝
server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
server_ctx.load_cert_chain(CERT, KEY)
server_ctx.minimum_version = ssl.TLSVersion.TLSv1_2

# 2. TLS 是 HTTP 下面的一层：先包装套接字，再由 HTTPServer 处理明文 HTTP
server = QuietServer(("127.0.0.1", 9443), Handler)
server.socket = server_ctx.wrap_socket(server.socket, server_side=True)
threading.Thread(target=server.serve_forever, daemon=True).start()


def probe(label, cafile=None, hostname="localhost"):
    # 3. 每个场景新建上下文，避免上一次的校验状态影响这一次
    ctx = ssl.create_default_context(cafile=cafile)  # cafile=None 时用系统信任库
    with socket.create_connection(("127.0.0.1", 9443), timeout=3) as raw:
        try:
            # 4. server_hostname 同时负责 SNI 和主机名校验，两者都依赖它
            with ctx.wrap_socket(raw, server_hostname=hostname) as tls:
                print(label, "OK", tls.version(), tls.cipher()[0])
        except ssl.SSLCertVerificationError as exc:
            print(label, "FAIL", exc.verify_code, exc.verify_message)


probe("A 系统信任库")                          # 自签证书不在系统信任库里
probe("B 手动信任 cert.pem", "cert.pem")        # 信任锚正确，域名也匹配
probe("C 域名不匹配", "cert.pem", "localhost.localdomain")
```

运行与预期输出（本机 Python 3.14 实测，套件名随平台略有差异）：

```bash
python3 tls_check.py
```

```text
A 系统信任库 FAIL 18 self-signed certificate
B 手动信任 cert.pem OK TLSv1.3 TLS_AES_256_GCM_SHA384
C 域名不匹配 FAIL 62 Hostname mismatch, certificate is not valid for 'localhost.localdomain'.
```

服务端用证书和私钥包装监听套接字，客户端新建上下文后发起握手，失败被 `SSLCertVerificationError` 捕获并打印错误码。三个场景共用同一台服务器，只改变信任锚与主机名，因此差异只可能来自校验环节：`cafile` 决定"信任谁"，`server_hostname` 同时是 SNI 和校验用的名字。`verify_code 18` 对应"自签证书、找不到可信签发者"，`62` 对应"链可信但域名对不上"。

## 动手实验

任务：为 `api.qingkong.example` 产出一份可执行的证书体检清单，并在本地离线复现两类拒绝。

前置条件：`python3.8+`、`openssl`、`curl`；步骤 1–3 离线即可完成，只有检查真实域名时需要网络。

1. 新建工作目录，用最小示例里的 `openssl req` 命令生成 1 天有效期的自签证书。
2. 把 `tls_check.py` 保存到同一目录并运行，确认输出与预期三行一致。
3. 先预测、再验证：把第三个探测的 `hostname` 改成 `api.qingkong.example`，运行后观察是否仍然失败。
4. 有网络时检查真实站点的链是否完整：

   ```bash
   openssl s_client -connect example.com:443 -servername example.com \
     -verify_return_error </dev/null
   ```

   预期输出（链长度随站点变化）：

   ```text
   depth=1 C=US, O=SSL Corporation, CN=Cloudflare TLS Issuing ECC CA 3
   depth=0 CN=example.com
   Protocol: TLSv1.3
   Verify return code: 0 (ok)
   ```

5. 按下表填写体检结论，每行都要能指向一条证据。

   | 检查项 | 执行方法 | 通过标准 |
   | --- | --- | --- |
   | 域名覆盖 | 查看 SAN | 目标域名在列表中 |
   | 链完整 | 数 `s_client` 输出的 `depth` 层数 | 不缺中间证书 |
   | 有效期 | 比较 `notAfter` 与当前时间 | 剩余天数大于续期窗口 |
   | 协议版本 | 看 `Protocol` 行 | TLS 1.2 及以上 |

预期结果：步骤 2 输出"一次成功、两次失败"；步骤 3 仍然失败，因为自签证书的 SAN 里没有 `api.qingkong.example`；步骤 4 的 `Verify return code` 为 0。

验证方法：三个探测的错误码分别为 18、0、62；步骤 4 若出现 `unable to verify the first certificate` 或 `depth` 层数不足，说明链不完整。清理：删除 `key.pem`、`cert.pem`、`tls_check.py`，并用 `lsof -nP -iTCP:9443 -sTCP:LISTEN` 确认端口已释放。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 报 `ERR_CERT_COMMON_NAME_INVALID` | SAN 未含访问域名，或客户端直接用 IP 访问 | `openssl x509 -in cert.pem -noout -ext subjectAltName` | 重签并把对外域名写入 SAN |
| 报 `ERR_CERT_AUTHORITY_INVALID`，根证书却没被替换 | 只下发叶证书，缺中间证书 | `openssl s_client -connect 主机:443 -servername 主机 -showcerts` 数证书数量 | 部署 `fullchain.pem`，叶证书在前 |
| 提示"证书已过期"，后台却显示在有效期内 | 客户端或服务器时钟偏差，`notBefore` 落在未来 | `date -u` 与 `notBefore` 对比 | 校准 NTP |
| 浏览器正常，Java 或旧版 Android 失败 | 最低版本设为 TLS 1.3，或套件不受支持 | `openssl s_client -tls1_2 -connect 主机:443` | 调整最低版本与套件，补齐中间证书 |
| 页面样式不加载，控制台报混合内容 | 页面里仍有 `http://` 资源，或被 HSTS 升级 | 控制台查看被拦截资源的协议 | 全站改 `https://`，逐步启用 HSTS |
| 换证书后 502 或 `handshake failure` | 私钥与证书不配对，或链顺序拼错 | 比对公钥：`openssl x509 -pubkey -noout -in cert.pem` | 重新配对，按叶→中间顺序拼接 |

## 安全与生产注意事项

**<u>证书私钥泄露等同于站点身份被完全冒用。</u>** 拿到私钥的人能伪装成 `api.qingkong.example` 与支付方通信。缓解：私钥只放在密钥管理服务或 HSM 中，权限 `600`，禁止进 Git 与构建日志，并预备吊销与轮换。

**<u>为了让报错消失而关闭证书校验，会把 HTTPS 退化成可被中间人篡改的通道。</u>** 常见形式是 `verify=False`、`curl -k`、`NODE_TLS_REJECT_UNAUTHORIZED=0`；攻击者可以替换任意响应内容，调用方毫无察觉。

**<u>证书过期是最高频的生产事故之一，而且它不产生错误日志。</u>** 那次 3 小时故障里应用日志完全安静，因为请求根本没进入应用。做法是设置到期前 30/14/7 天三级告警，自动续期后验证进程确实加载了新证书。

## 本课总结

- HTTPS 同时提供三件事：证明对端身份、协商会话密钥、加密并校验传输内容。
- 证书把域名和公钥绑定，私钥只用于签名，任何时候都不应离开服务端。
- 客户端按"建链、验签、有效期、域名与用途、吊销"五步校验，任何一步失败都在 HTTP 之前终止。
- 握手协商出的对称密钥才是加密应用数据的钥匙，证书本身不负责加密流量。
- TLS 终止位置、证书续期责任和临期告警，是上线前必须写清的三件事。

## 思考题

晴空商城把 `shop.qingkong.example` 的 TLS 终止在 CDN，但源站 `origin.qingkong.example` 仍可从公网直达，支付回调也直接打到源站。请分析：是否应在源站再启用 TLS，甚至加上 mTLS？请从"谁能看到明文""证书由谁续期""失效时如何发现"三个角度给出判断，并说明方案会新增哪些运维成本。

参考思路：先画信任边界，而不是先选技术。源站可从公网直达时，CDN 上的证书与 WAF 都能被绕过，源站启用 TLS 是必要的；若调用方只有 CDN 和支付方，mTLS 能缩小攻击面，但引入客户端证书的分发、轮换与吊销成本。可比较"源站只允许 CDN 网段""支付回调单独端到端 TLS""全量 mTLS"三种方案，并明确谁负责续期。

## 小测

1. 服务端证书里通常包含以下哪一项？  
   A. 服务器私钥　B. 服务器公钥　C. 客户端会话密钥　D. 数据库连接串
2. 握手完成后，HTTP 报文用哪种密钥加密？  
   A. 服务端私钥　B. 客户端私钥　C. 本次握手协商出的对称会话密钥　D. 根证书中的公钥
3. 客户端验证服务端证书时，至少要检查哪三件事？
4. 通配符证书 `*.qingkong.example` 能否覆盖 `api.staging.qingkong.example`？为什么？
5. 场景题：值班同学把客户端改成 `verify=False` 绕过证书报错后接口通了，并提交上线。你应该如何评估和处理？

## 答案与解析

1. **B。**证书把域名与公钥绑定并由 CA 签名。A 绝不能放进证书；C 在握手时才临时协商；D 与证书无关。
2. **C。**非对称运算只用于身份验证和密钥协商，之后用对称密钥加密，因为后者快得多。A、B 都不用于加密应用数据；D 只是信任锚里的公钥，从不参与会话加密。
3. 建链（追溯到信任库中的根证书）、逐级验签、查有效期、查主机名是否在 SAN 中、查 EKU 用途，并尽量查吊销。少做任何一项，都可能让"看起来正常的连接"被接受。
4. **不能。**通配符只匹配一级子域：`*.qingkong.example` 覆盖 `api.qingkong.example`，不覆盖 `api.staging.qingkong.example`。
5. **不能接受上线。**`verify=False` 关闭了身份验证，攻击者可以替换支付接口的响应，等于把资金相关调用交给中间人。正确做法是查明缺中间证书、域名不匹配还是过期；确需自签证书时，应把对应 CA 显式加入信任库，并检查同类改动是否已扩散。

### 动手实验参考

步骤 2 的错误码应为 18（自签、无可信签发者）、0（成功）、62（主机名不匹配）。步骤 3 修改主机名后仍会失败，因为 SAN 只含 `localhost`。步骤 4 的 `Verify return code: 0 (ok)` 表示链完整；若出现 `unable to verify the first certificate`，优先怀疑中间证书缺失。

## 延伸阅读与下一课

- MDN：[HTTPS](https://developer.mozilla.org/zh-CN/docs/Glossary/HTTPS) 与 [Strict-Transport-Security](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security)。
- RFC 8446：[The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446)。
- RFC 5280：[Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280)。
- Python 官方文档：[ssl — TLS/SSL wrapper for socket objects](https://docs.python.org/3/library/ssl.html)。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[Header、Cookie 与缓存](04-headers-cookies-and-caching.md)。
- 下一课：[JSON、XML、CSV 与字符编码](06-json-xml-and-encoding.md)。
