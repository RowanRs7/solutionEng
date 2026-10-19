---
title: 对象存储与文件管理
slug: object-storage-and-file-management
module: traditional-solutions
stage: design
type: core
difficulty: beginner
duration: 45m
prerequisites:
  - nosql-redis-and-caching
outcomes:
  - 解释对象存储的桶、键、对象与版本语义，说明为什么它没有目录和就地修改
  - 写出一次预签名直传的完整流程，指出票据必须签住哪些字段
  - 为四类文件各选一种下发方式，并写出一条可执行的生命周期规则
last_reviewed: 2026-10-19
---

# 对象存储与文件管理

## 为什么需要学习

晴空商城第一版把退款凭证照片塞进订单库的 `BLOB` 列，理由很朴素：文件也是数据，存一起最省事。半年后单库备份涨到 400GB，`select *` 一次就拖满连接池；第二版改存应用服务器本地盘，两台机器各存一半，顾客点开退款页一半 404，扩容加机器还会丢文件。

两次翻车都不是“存储不够大”，而是没人说清文件该放在哪、谁能取、留多久。

> **核心结论：** 对象存储把“保存文件”简化成“用键取字节”，代价是把权限、生命周期和一致性全部显式交给你自己设计。

## 学习目标

完成本课后，你能够：

- 解释*桶*、*对象键*、*对象*和*版本控制*的语义，说明为什么没有目录、重命名和就地修改。
- 写出一次“申请票据 → 直传 → 回调确认”的流程，指出信任边界落在哪一跳。
- 在公有 URL、*预签名 URL*、CDN 鉴权与服务端代理之间选型，说明各自的暴露面。
- 为四类文件各写一条可执行的生命周期规则，说明版本与副本如何清理。

## 前置知识

- 回看上一课：[NoSQL、Redis 与缓存失效](03-nosql-redis-and-caching.md)。
- 知道 HTTP 的 `Content-Type`、`Content-Length` 与 `4xx` / `5xx` 各表达什么。
- 知道认证与授权是两问：谁在请求，和能不能做这件事。
- 能读懂 Python 3 标准库代码（`hashlib`、`hmac`、`secrets`）。

## 业务场景

晴空商城的四类文件落在同一套存储里，要求却完全不同：

- **商品主图**：读多写少、允许公开、要 CDN 与多尺寸；上传者是品牌商，审核前不能对外。
- **退款凭证**：顾客拍的破损照，客服与风控要看，<u>绝不能被搜索引擎或爬虫碰到</u>。
- **面单与发票**：出库或开票时生成 PDF，财务留 10 年，客服只在工单里点链接。
- **客服录音**：单个 30–200MB，上传即落，按 180 天清理。

架构师这轮要交付：键的布局规范、上传流程的信任边界、四类文件的下发方式、生命周期规则。

## 核心概念

*对象存储*用 HTTP 存取不可变的字节块：写入是整个对象的替换，不是就地改第 100 个字节。**它的简单是“能力少”，不是“不用管”。**

| 概念 | 含义 | 晴空商城示例 |
| --- | --- | --- |
| *桶*（bucket） | 命名空间 + 地域 + 权限与生命周期的边界 | `qingkong-refund-evidence` |
| *对象键*（object key） | 桶内唯一字符串，`/` 只是普通字符 | `refunds/2026/10/SO-20261019-0042/b05f.jpg` |
| *对象* | 键 + 字节 + 元数据 + *ETag* | 一张 2MB 的 JPEG 及其 `content-type` |
| *版本控制* | 同键多次写入都保留，删除只加标记 | 覆盖上传后旧凭证仍可读 |
| *分片上传* | 拆块并发上传再合并，中断留残片 | 200MB 的客服录音 |

*ETag* 是存储服务给的对象标识，能比对两次上传是否同一字节流，但不能当业务幂等键。控制台里的“文件夹”只是把共享前缀折叠显示：<u>没有目录，就没有原子的“移动目录”</u>，重命名等于复制加删旧，对百万对象逐一致命地慢。

*预签名 URL* 是服务端用密钥算出的、带过期的授权链接，持有者在过期前能以签发者身份读写那一个对象。*直传*指浏览器拿着它把字节直接发给存储，服务不转发内容。

| 下发方式 | 谁能打开 | 暴露面 | 适用 |
| --- | --- | --- | --- |
| 公有 URL | 所有人 | 流到哪都能看，撤销不了 | 商品主图 |
| 预签名 URL | 拿到链接的人 | 过期前等同通行证，会留痕 | 凭证、发票、录音 |
| CDN 鉴权（签名 Cookie） | 通过 CDN 校验的会话 | 回源凭证泄露即可绕过 | 大流量付费内容 |
| 服务端代理 | 通过业务鉴权的请求 | 字节过应用，占带宽与内存 | 小文件、需逐次审计 |

## 工作原理

以“顾客上传一张退款凭证、客服三天后查看”为主线：

1. **申请票据**：小程序带订单号、文件名与声明类型，向业务服务请求上传凭据。
2. **服务端签发**：服务确认订单属于该用户、类型在白名单内，自己生成键（前缀锁订单 + 随机主体），把键、类型、上限、过期时间一起签名后返回预签名 URL。
3. **浏览器直传**：客户端把字节直接 `PUT` 到存储；业务服务不碰内容，也不承担带宽与超时。
4. **回调确认**：客户端把键回报给业务，服务读对象元数据（大小、类型、ETag）核对，才写引用。**<u>客户端说“传好了”不算事实，“元数据对得上”才算。</u>**
5. **下发查看**：客服页面拿到服务端每次现签的短过期 URL，而不是桶的公有地址。
6. **生命周期**：存储按前缀与标签执行规则——30 天转低频、180 天转归档、365 天过期删除，并清理残片与旧版本。
7. **删除与验证**：先删引用再删对象（或相反），再抽样确认版本、CDN 缓存与工单附件都不可取。

第 2 步和第 6 步才是架构师要写进方案的部分：键的布局决定生命周期能否按前缀生效，签名覆盖哪些字段决定客户端还剩多少自由。

## 架构与选型

| 方案 | 适用 | 不适用或需注意 | 主要权衡 |
| --- | --- | --- | --- |
| 数据库 BLOB 列 | 极小附件，须与业务行同事务 | 备份膨胀，大字段挤占连接池 | 一致性最强，扩展性最差 |
| 应用服务器本地盘 | 单机工具、临时文件 | 多实例互不可见，扩缩容即丢文件 | 最简单，不可水平扩展 |
| 网络文件系统 | 老代码要求 POSIX 语义 | 高并发写与锁竞争，跨可用区延迟高 | 兼容性好，运维负担重 |
| 对象存储 + 直传 | 图片、音视频、文档、发票 | 无目录原子操作、无跨对象事务 | 弹性与成本最好，权限要自建 |
| 对象存储 + CDN | 读多写少、要全球加速 | 缓存让删除不立即生效 | 延迟低，一致性变弱 |

选型先问四个问题：**要不要和数据库行同事务？读多还是写多？会不会被公开访问？留多久、谁能删？** 只有答案里出现“必须原子”或“必须 POSIX 语义”时，才轮到 BLOB 或网络文件系统；否则默认对象存储，权限与生命周期就是必须交付的设计。

## 最小示例

问题：只用 Python 3 标准库实现“签发票据 + 校验票据”的闭环，证明客户端既改不了键，也改不了类型与上限。环境 Python 3.9+，不联网；用 HMAC 代替厂商签名算法，语义一一对应（真实预签名 URL 把同样几类信息放进签名范围与查询参数）。

```python
import hashlib
import hmac
import secrets
import time

SECRET = b"dev-only-secret"              # 生产由密钥管理服务下发，代码和仓库都不持有
BUCKET = "qingkong-refund-evidence"
ALLOWED_TYPES = {"image/jpeg", "image/png", "application/pdf"}
MAX_BYTES = 8 * 1024 * 1024              # 单张凭证 8MB，超了让人重拍而不是放开上限


def object_key(order_id, filename, now):
    # 键由服务端拼：前缀绑定订单，主体换成随机串，客户端只能决定扩展名
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    stamp = time.strftime("%Y/%m", time.gmtime(now))
    return f"refunds/{stamp}/{order_id}/{secrets.token_hex(8)}.{suffix}"


def sign(key, content_type, max_bytes, expires_at):
    # 四个字段一起进 HMAC：改键、改类型、改上限、改过期任一项，签名都对不上
    message = f"{key}|{content_type}|{max_bytes}|{expires_at}".encode()
    return hmac.new(SECRET, message, hashlib.sha256).hexdigest()


def issue_ticket(order_id, filename, content_type, now):
    if content_type not in ALLOWED_TYPES:      # 白名单在签发端就拦，不靠前端校验
        raise ValueError(f"unsupported content_type: {content_type}")
    key = object_key(order_id, filename, now)
    expires_at = int(now) + 300                # 五分钟，够传一张照片，不够被转发滥用
    return {
        "bucket": BUCKET, "key": key, "content_type": content_type,
        "max_bytes": MAX_BYTES, "expires_at": expires_at,
        "signature": sign(key, content_type, MAX_BYTES, expires_at),
    }


def verify_upload(ticket, received_type, actual_bytes, now):
    # 先用票据自身字段重算签名：任何字段被改都会在这里被拒
    expected = sign(ticket["key"], ticket["content_type"],
                    ticket["max_bytes"], ticket["expires_at"])
    if not hmac.compare_digest(expected, ticket["signature"]):
        return "reject: signature mismatch"
    # 签名有效之后，才轮到比较实际发来的东西与票据是否一致
    if received_type not in ALLOWED_TYPES:
        return "reject: content_type not allowed"
    if received_type != ticket["content_type"]:
        return "reject: content_type differs from ticket"
    if now > ticket["expires_at"]:
        return "reject: ticket expired"
    if actual_bytes > ticket["max_bytes"]:
        return "reject: object too large"
    return "accept"


NOW = 1792404000  # 2026-10-19T10:00:00Z
t = issue_ticket("SO-20261019-0042", "IMG_0042.JPG", "image/jpeg", NOW)
print("key:", t["key"])
print("1 正常上传        ", verify_upload(t, "image/jpeg", 2 * 1024 * 1024, NOW))
print("2 键被改成发票目录", verify_upload({**t, "key": "invoices/SO-20261018-0007/x.pdf"},
                                        "application/pdf", 1024, NOW))
print("3 上限被改成 1GB  ", verify_upload({**t, "max_bytes": 1024 ** 3},
                                        "image/jpeg", 2 * 1024 * 1024, NOW))
print("4 类型换成 png    ", verify_upload(t, "image/png", 1024, NOW))
print("5 过期后重放      ", verify_upload(t, "image/jpeg", 1024, NOW + 301))
print("6 传了 9MB        ", verify_upload(t, "image/jpeg", 9 * 1024 * 1024, NOW))
evil = issue_ticket("SO-20261019-0042", "../../../invoices/SO-20261018-0007/x.PDF",
                    "application/pdf", NOW)
print("恶意文件名的键     ", evil["key"])
```

保存为 `ticket.py` 后运行 `python3 ticket.py`。预期输出（随机十六进制段每次不同）：

```text
key: refunds/2026/10/SO-20261019-0042/b05fdf6a56e3b98d.jpg
1 正常上传         accept
2 键被改成发票目录 reject: signature mismatch
3 上限被改成 1GB   reject: signature mismatch
4 类型换成 png     reject: content_type differs from ticket
5 过期后重放       reject: ticket expired
6 传了 9MB         reject: object too large
恶意文件名的键      refunds/2026/10/SO-20261019-0042/4accfd36f07fa60b.pdf
```

四处设计值得记住：签名覆盖键、类型、上限、过期四项，所以第 2、3 例连“改哪个字段”都无从下手；<u>必须先 `hmac.compare_digest` 验签再看策略</u>，否则篡改者能靠错误信息反推规则；恶意文件名 `../../../invoices/...` 只影响扩展名，键仍在 `refunds/` 前缀下；`text/html` 不在白名单，连比对都过不去。

## 动手实验

前置条件：已跑通最小示例，Python 3.9+，只用构造数据。

1. 给 `verify_upload` 加一条规则：`image/svg+xml` 直接拒绝，并写下为什么 SVG 不能与 JPEG 同列。
2. 用同一订单号连签 5 张票据并打印键，确认主体不同、前缀相同。
3. 写 8 行对象清单（键、大小、创建时间、是否含旧版本），按“30 天转低频、180 天过期、只删非当前版本”算出每行处置。
4. 把 `MAX_BYTES` 改成 1GB 后重跑第 6 个用例，记录结果如何变化。
5. 签一张 300 秒票据，把校验时的 `now` 往后推 600 秒，说明服务端为什么无法“提前作废”它。

预期结果：SVG 被拒；5 个键前缀一致，说明生命周期能按前缀命中；删除只落在非当前版本，当前版本继续按时间转冷；同一个 9MB 文件由 `reject` 变 `accept`，说明上限是唯一防线；已签出的 URL 无法提前作废——这正是短过期比“记得撤销”可靠的原因。

验证方法：键清单里不应出现 `..`、原始文件名、手机号或邮箱；同一订单的键应能被一个 `refunds/2026/10/<订单号>/` 前缀全部命中。

清理方法：删除临时脚本与生成对象，清掉未完成的分片；不要把真实凭证照片留在本地或提交进仓库。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 未登录也能打开凭证图片 | 桶或对象被设成公有读 | 退出登录后 `curl -I` 直取对象 URL | 关闭公有读、开启桶级公有访问阻断，改用短过期签名 URL |
| 上传大文件随机失败 | 单次 PUT 撞上网关或客户端超时 | 看网关超时日志与失败对象的大小分布 | 改分片上传加直传，重试逻辑放在分片粒度 |
| 对象已删除，链接仍能打开 | 版本控制留着旧版本，CDN 还有缓存 | 列对象版本，再绕缓存直连源站取一次 | 删版本与删除标记、刷新 CDN、把清理写进生命周期 |
| 文件名含中文或空格后 404 | 键未做 URL 编码，或客户端自己拼路径 | 对比原始键与请求路径 | 键只留 ASCII 与随机串，展示名存数据库 |
| 上传的图片被浏览器当网页执行 | `Content-Type` 信客户端，缺 `Content-Disposition` | 直接访问对象看响应头 | 服务端落定 `Content-Type`，加 `nosniff` |

## 安全与生产注意事项

**<u>把退款凭证所在的桶设成公有读，等于把顾客家里的照片放在公开互联网上。</u>** 键里常带订单号与日期，爬虫按前缀遍历几分钟就能批量枚举；被抓取后即使删除也追不回副本。缓解：默认私有、开启桶级公有访问阻断、下发只走短过期签名 URL，并把“桶策略变更”列为需评审的生产变更。

**<u>预签名 URL 在过期前就是一张无需登录的通行证，还会留在浏览器历史、网关日志与客服的聊天截图里。</u>** 任何拿到链接的人都能以签发者身份读写那一个对象，服务端无法提前吊销。缓解：按需现签、过期压到分钟级、一个 URL 只对一个键；需要长期可读就换 CDN 鉴权。

**<u>删除对象不等于删除副本：旧版本、CDN 缓存、工单附件和备份里的对象仍然可读。</u>** 顾客注销后数据仍能被复现，团队也拿不出删除证据。缓解：列出“每类文件有哪些副本”，删除覆盖版本、缓存与备份过期。

## 本课总结

- **对象存储是“用键换字节”**：不可变、无目录、无跨对象事务，权限与生命周期都得自己配。
- **直传把带宽压力挪出应用服务，把信任边界挪到票据上**：票据签住什么，客户端就只能改什么。
- **服务端生成的键是安全资产**：前缀锁业务、主体随机、只留扩展名，才挡得住路径穿越与枚举。
- **下发方式决定暴露面**：公有 URL 撤销不了，签名 URL 能用到期，CDN 鉴权适合大流量付费内容。
- **生命周期必须显式写**：转冷、过期、清版本、清残片，缺一件账单或合规就会漏。

## 思考题

晴空商城想让 AI 客服看退款凭证，判断“破损是否属实”。桶目前全部私有、客服只能逐张点开，产品希望“模型也能看图，响应更快”。请设计这条链路：图片经谁读取、以什么身份、用多长过期的 URL，供应商侧会留下什么副本，180 天清理规则如何覆盖新增的一环。

参考思路：不要把桶改公有，也不下发长效 URL。让业务服务以自身身份读对象，转成短过期链接或直接把字节放进请求体，两者都不进业务日志。真正要回答的是：供应商是否留存、留多久、是否用于训练；清理要覆盖对象、缩略图与供应商侧缓存，无法覆盖时如何向顾客披露——这属于合规判断，需法务确认。

## 小测

1. 下面哪件事在对象存储里可以一次原子完成？  
   A. 修改对象第 100 个字节　B. 整体替换一个对象　C. 重命名一个前缀下的全部对象　D. 在对象末尾追加一段
2. 直传相比“浏览器先传业务服务再转存存储”，主要改变了什么？  
   A. 文件变得更安全　B. 字节不再经过业务服务，带宽与超时压力转移　C. 不再需要鉴权　D. 对象自动获得版本控制
3. 预签名 URL 的过期时间应当由谁决定？为什么？
4. 为什么对象键里不应保留用户上传的原始文件名？
5. 场景题：品牌商把商品主图传进公有读的图片桶，某张图侵权要立刻下架，但删除后用户仍能打开旧图。请指出至少两个原因，并给出处置顺序。

## 答案与解析

1. **B。** 对象不可变，写入即整体替换。A、D 都得先取回再整体重写；C 要逐个复制删除，没有跨对象原子操作。
2. **B。** 直传把字节路径挪到浏览器与存储之间。A 不成立，安全取决于票据与桶策略；C 仍要鉴权，只是换成签名；D 版本控制是桶级配置，与上传路径无关。
3. 由服务端决定，按“这次操作真正需要多久”来定：上传取分钟级，下载按一次会话长度。长过期票据就是长效通行证，签出去收不回来。
4. 原始文件名是用户可控输入，可能含 `..`、`/`、超长字节、手机号，既能穿越前缀也能泄露信息；它也不唯一，直接当键会互相覆盖。展示名存数据库，键用随机串。
5. 原因一，桶是公有读，删除后 CDN 与各地缓存仍持有副本；原因二，开了版本控制，删除只加标记，旧版本还在；原因三，链接已被外部转存，删源站也管不到。处置顺序：先把该键收紧为鉴权访问并刷缓存 → 删所有版本与标记 → 换成占位图或返回 410 → 留处置时间与证据。是否追究侵权属于法务判断。

### 动手实验参考

第 1 步应拒绝 SVG：它可内嵌脚本，被浏览器直接打开时等同 XSS，所以白名单要按具体位图格式列，而不是“凡是 `image/*` 都放行”。第 2 步键主体不同、前缀相同，正是生命周期能按前缀命中的前提。第 3 步只删非当前版本，避免“清理旧版本”顺手删掉在用的对象。第 4 步放开的是“能传多大”，不是“能不能传”。第 5 步说明签名 URL 不可提前撤销，短过期是主要防线。

## 延伸阅读与下一课

- [Amazon S3：使用预签名 URL 共享对象](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)：签名范围与失效条件。
- [Amazon S3：对象生命周期管理](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html)：转存储类、过期删除与版本清理。
- [Amazon S3：阻断公有访问](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html)：公有访问拦截。
- [OWASP 文件上传备忘单](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)：类型校验与执行风险清单。
- [Amazon S3 API：PutObject](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html)：单次上传的请求头与响应。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[NoSQL、Redis 与缓存失效](03-nosql-redis-and-caching.md)。
- 下一课：[时间、金额、UUID 与编码陷阱](05-time-money-uuid-and-encoding.md)。
