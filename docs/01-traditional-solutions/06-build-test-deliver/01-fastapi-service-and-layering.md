---
title: FastAPI 最小服务与项目分层
slug: fastapi-service-and-layering
module: traditional-solutions
stage: build-and-integrate
type: core
difficulty: beginner
duration: 60m
prerequisites:
  - data-and-architecture-overview
outcomes:
  - 用 FastAPI 起一个带参数校验与依赖注入的退款查询服务，并能说出 200、404、422 分别由哪一层产生
  - 区分接口层、服务层、仓储层各自负责与不负责的内容，判断一段代码该落在哪一层
  - 用 `Depends` 注入配置与仓储，并解释为什么不在模块顶层读取配置
  - 用 `python3` 标准库脚本验证依赖解析顺序与审核阈值规则，不依赖外部服务
last_reviewed: 2026-10-19
---

# FastAPI 最小服务与项目分层

## 为什么需要学习

晴空商城的退款服务最初只是一个 60 行的 `main.py`：三个路由，直接连数据库，直接调支付。半年后它长到 1900 行：金额阈值判断、状态流转校验、支付签名、SQL 和打印日志混在同一个文件里。

症状很具体：把“超额退款转人工审核”这条规则从 500 元调到 300 元，要改四个接口；客服工作台和风控后台各有一份重复的金额判断，已经对不上；想测“超过阈值”这个分支，必须先启动数据库和支付沙箱；新人第一次改字段，顺手把支付回调也改成了 `400`。

代码本身没有写错，是没给变化留位置。分层与依赖注入要解决的就是这件事：让每类改动落在可预期的地方，且能单独验证。

> **核心结论：** 分层不是为了让目录好看，而是把“改一处”的影响范围压缩到可检查的边界内。

## 学习目标

完成本课后，你能够：

- 用 FastAPI 起一个只读退款查询服务，路径参数、响应模型与错误状态码都可验证。
- 说明接口层、服务层、仓储层各自负责什么、明确不负责什么。
- 用 `Depends` 把配置与仓储注入到路由，并解释为什么不在模块顶层读取配置。
- 判断一段代码该落在哪一层，并说出越层调用带来的具体后果。
- 用 `python3` 标准库脚本验证依赖解析顺序与审核阈值规则，不依赖数据库和网络。

## 前置知识

- 回看上一单元：[数据与应用架构](../05-data-and-architecture/00-overview.md)。
- 能读懂 Python 3 的函数、类型注解和 `from x import y`。
- 知道 HTTP 方法与状态码的分工：`200` 成功、`404` 不存在、`422` 入参不合法。
- 知道数据库表“主键”的含义，但本课不需要真的连数据库。

## 业务场景

“晴空商城”的客服工作台要查一笔退款：订单号、退款金额、是否超过人工审核阈值、下一步由谁处理。查完之后，客服可能还要提交一条新的退款申请。

参与者与约束：客服工作台只认 JSON；风控后台要复用同一套业务规则；退款服务不得把内部表结构暴露给调用方；审核阈值会按大促调整，也要按环境（开发、预发、生产）分别配置；财务对账批处理在夜跑时也要判断“该不该人工审核”。

本课只处理开发侧面——从零起一个能跑的服务骨架，把“协议、规则、存储”三件事拆开，为后面的异常处理、结构化日志、测试和容器化打地基。

## 核心概念

*接口层*（也叫路由层、HTTP 层）只做三件事：解析入参、调用服务、把结果或异常翻译成 HTTP 语义。它不判断业务规则，不写 SQL。

*服务层*承载业务规则：金额是否超过审核阈值、这个状态是否允许再次提交。**同一套规则在 HTTP 接口、命令行脚本和定时任务里应当只有一份实现**，所以规则住在这里。

*仓储层*封装数据存取：按主键查询、写入、加锁。它回答“数据长什么样”，不回答“这样的数据能不能退款”。即便只是把 ORM 包一层，仓储层依然有价值——它给服务层一个可替换的接缝。

*依赖注入*（Dependency Injection）指对象不自己创建依赖，而由外部传入。FastAPI 用 `Depends` 把这件事声明化：路由签名里写清需要什么，框架负责构造与传递。

*依赖覆盖*（dependency override）是测试期的替换机制：用 `app.dependency_overrides` 把真实仓储换成内存假实现，接口层与服务层都能离线测。

*请求模型*与*响应模型*是 Pydantic 类，分别约束“进来的 JSON 必须有什么”和“出去的 JSON 允许有什么”。

| 层 | 负责 | 明确不负责 | 晴空商城示例 | 谁最常改它 |
| --- | --- | --- | --- | --- |
| 接口层 | 路径、参数校验、状态码、序列化 | 业务阈值、SQL、事务 | `GET /refunds/{id}` | 前端联调、契约变更 |
| 服务层 | 业务规则、流程编排、事务边界 | HTTP 概念、具体表结构 | 超额转人工审核 | 产品规则变更 |
| 仓储层 | 查询、写入、并发控制 | 业务判断、协议格式 | `refunds` 表读写 | 表结构与索引变更 |

## 工作原理

一次 `GET /refunds/R-1` 的完整生命周期：

1. **连接与解析**：Uvicorn 接收 TCP 连接，按 HTTP 解析出方法、路径和请求头，组装成 ASGI 的 `scope` 与 `receive`，交给应用对象。
2. **路由匹配**：FastAPI 查路由表。路径存在但方法不符返回 `405`；路径不存在返回 `404`。这一步还没进你的代码。
3. **依赖解析**：框架看到签名里的 `Depends(get_service)`，递归求值依赖链——配置、仓储、服务依次构造。**同一请求内同一依赖默认只求值一次**，所以配置不会被重复读取。
4. **入参校验**：路径参数、查询参数和请求体按声明的类型转换并校验。不合格直接返回 `422`，路由函数根本不会被调用。
5. **进入接口层**：路由函数拿到已就绪的服务对象，只写一行调用，不做条件判断。
6. **执行规则**：服务层取数据、判断阈值与状态，得出“自动通过”还是“转人工审核”。需要写入时，在自己的边界内开启事务。
7. **返回与翻译**：服务返回普通数据结构，`response_model` 裁剪字段并序列化；领域异常在边界上被翻译成 `404`、`409` 等。

第 3 步和第 7 步是理解 FastAPI 的关键：它是一根装配线，把配置、存储、业务对象接到一起，再把你返回的东西变成 JSON。你的业务代码不必知道这些装配细节，因此可以脱离 HTTP 单独运行。

## 架构与选型

| 方案 | 适用 | 不适用或代价 | 判断依据 |
| --- | --- | --- | --- |
| 单文件 `main.py` | 原型、一次性脚本、5 个以内的只读接口 | 规则重复、测试要连数据库、无法并行开发 | 是否活不过两周 |
| 两层（路由 + 服务） | 逻辑简单，数据访问只是几行查询 | 换存储或加缓存时要改服务层 | 近期是否可能换存储 |
| 三层（接口 / 服务 / 仓储） | 有真实业务规则、多人协作、需要离线测试 | 多几个文件、多一层转发 | 是否存在一条值得单测的业务规则 |
| 整洁架构（实体 / 用例 / 适配器 / 端口） | 长期演进、多入口（HTTP、消息、批处理） | 对小服务是过度设计，样板代码多 | 规则是否要在 3 个以上入口复用 |

选型顺序：先数一数“值得写单测的业务规则”有几条，再决定是否引入服务层；只有确实要在 HTTP 之外复用同一套规则时，才需要端口与适配器。**分层应按变化频率切，不按文件数量切。** 若一个服务只有增删改查，硬套四层只会让读代码的人多跳三次。

## 最小示例

问题：验证分层是否真的把“配置、存储、规则”分开，以及依赖按什么顺序解析。

环境：Python 3.9 及以上，只用标准库，不装任何包。

```python
"""layers_check.py：只用标准库验证分层与依赖注入的调用顺序。"""
from dataclasses import dataclass          # 用不可变数据类承载配置，避免运行中被改写


@dataclass(frozen=True)
class Settings:
    auto_approve_limit_cents: int = 50000  # 500 元以下自动通过，金额单位是分


class RefundRepository:
    """仓储层：只做存取，不判断业务规则。"""

    def __init__(self, rows):
        self._rows = rows                  # 用内存字典代替数据库，便于离线验证

    def find(self, refund_id):
        return self._rows.get(refund_id)   # 查不到返回 None，不抛 HTTP 异常


class RefundService:
    """服务层：业务规则的唯一归属地。"""

    def __init__(self, repo, settings):
        self._repo = repo                  # 依赖由外部传入，服务层不自己 new
        self._settings = settings

    def decide(self, refund_id):
        row = self._repo.find(refund_id)   # 只经仓储取数，不碰 SQL、不碰 HTTP
        if row is None:                    # “不存在”是业务结论，用领域异常表达
            raise LookupError(refund_id)   # 接口层再把它翻译成 404
        auto = row["amount_cents"] <= self._settings.auto_approve_limit_cents
        return {
            "id": refund_id,
            "status": row["status"],
            "next_action": "auto_approve" if auto else "manual_review",
        }


def get_settings():
    print("  [容器] 构造 Settings")        # 打印顺序，证明配置被解析了一次
    return Settings()


def get_service():
    rows = {
        "R-1": {"status": "accepted", "amount_cents": 19900},
        "R-2": {"status": "accepted", "amount_cents": 88000},
    }
    repo = RefundRepository(rows)          # 先解析叶子依赖：仓储
    settings = get_settings()              # 再解析配置，仍只构造一次
    print("  [容器] 构造 RefundService")   # 最后组装：服务只依赖抽象好的入参
    return RefundService(repo, settings)


if __name__ == "__main__":
    service = get_service()                # 相当于 FastAPI 在请求前解析 Depends
    for refund_id in ("R-1", "R-2", "R-9"):
        try:
            print(refund_id, "->", service.decide(refund_id))
        except LookupError as exc:
            print(refund_id, "-> 404 not_found", exc)
```

运行与真实输出（Python 3.14.7 实跑）：

```bash
python3 layers_check.py
```

```text
  [容器] 构造 Settings
  [容器] 构造 RefundService
R-1 -> {'id': 'R-1', 'status': 'accepted', 'next_action': 'auto_approve'}
R-2 -> {'id': 'R-2', 'status': 'accepted', 'next_action': 'manual_review'}
R-9 -> 404 not_found R-9
```

整体流程：`get_service` 扮演容器，先建仓储、再建配置、最后组装服务；`decide` 只经仓储取数并应用一条阈值规则；不存在的情况抛领域异常，由调用方决定翻译成什么。关键取舍是**让服务层完全不知道 HTTP 存在**，所以同一段规则可以在测试、脚本和接口里复用。

同样的职责在 FastAPI 里是这样写的（需 `pip install fastapi uvicorn`，本课不安装）：

```python
# app/api/refunds.py —— 接口层：解析、调用、翻译，仅此三件事
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/refunds", tags=["refunds"])


class RefundOut(BaseModel):                  # 响应模型：允许出网的字段白名单
    id: str
    status: str
    next_action: str


@router.get("/{refund_id}", response_model=RefundOut)
def read_refund(refund_id: str, service=Depends(get_service)):   # 服务由容器注入
    try:
        return service.decide(refund_id)     # 路由里没有 if、没有 SQL、没有 try 之外的逻辑
    except LookupError:                      # 领域异常 → HTTP 语义，只在边界翻译
        raise HTTPException(status_code=404, detail="refund_not_found")
```

关键设计选择：`service=Depends(...)` 让路由不需要知道服务如何构造，测试时换成假实现即可；`response_model` 保证客户手机号、内部备注等字段不会被顺手返回；`LookupError → 404` 的翻译只发生在边界，服务层因此能在命令行里复用。

预期输出（本次写作未启动 uvicorn，以下为按框架默认行为推导的结果）：

```text
$ curl -i http://127.0.0.1:8000/refunds/R-1
HTTP/1.1 200 OK
{"id":"R-1","status":"accepted","next_action":"auto_approve"}

$ curl -i http://127.0.0.1:8000/refunds/R-9
HTTP/1.1 404 Not Found
{"detail":"refund_not_found"}
```

测试期替换依赖，不必连数据库：

```python
app.dependency_overrides[get_service] = lambda: FakeService()   # 只影响当前测试用例
```

## 动手实验

### 任务：把一条业务规则放进服务层并验证

前置条件：Python 3.9 及以上；工作目录 `/tmp/refund_lab`；只用标准库，无需 `8000` 端口。

1. 创建目录并把最小示例保存为 `/tmp/refund_lab/layers_check.py`。
2. 运行 `python3 layers_check.py`，对照上文输出，确认 `R-1` 为 `auto_approve`、`R-2` 为 `manual_review`。
3. 把 `auto_approve_limit_cents` 从 `50000` 改为 `15000`，重跑，观察 `R-1` 的 `next_action` 是否翻转。
4. 给服务层加一条新规则：`status` 为 `closed` 的退款即使金额很小也不自动通过。在内存数据里加一条 `"R-3": {"status": "closed", "amount_cents": 100}`。
5. 只修改 `RefundService.decide`，不修改仓储层，也不修改 `__main__` 里的调用代码。

预期结果：步骤 3 后 `R-1` 变为 `manual_review`（19900 分 > 15000 分）；步骤 4 后 `R-3` 也是 `manual_review`。

验证方法：输出行的 `next_action` 与预期一致；`RefundRepository` 与 `__main__` 部分一字未改，说明规则改动没有扩散到存储和调用方——这正是分层要买的东西。

清理方法：`rm -rf /tmp/refund_lab`。若后续用 uvicorn 起了调试服务，用 `Ctrl+C` 或 `kill` 结束，别把 `--reload` 的服务留在共享主机上。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 调一条审核规则要改四个路由文件 | 规则被复制进了接口层 | 在路由文件里搜阈值数字、`amount`、`if` | 规则收敛到服务层，路由只保留一次调用 |
| 单测一个分支必须先起数据库 | 服务层自己创建连接或依赖具体 ORM | 看服务构造函数里是否 `new` 了连接 | 注入仓储，测试传内存实现 |
| 服务启动即崩，报 `KeyError: 'REFUND_DB_URL'` | 配置在模块顶层读取，导入时就求值 | 用 `python3 -c "import app"` 单独复现 | 改为 `Depends` 工厂或启动时显式校验配置 |
| 压测后报连接池耗尽，连接数不回落 | 依赖里建了会话但没释放 | 观察数据库连接数是否随请求单调增长 | 用 `yield` 依赖并在 `finally` 关闭，设置池上限 |
| 客户端收到 `422`，服务端日志里没有任何记录 | 请求体不匹配 `BaseModel`，框架在进路由前就拒了 | 看响应体 `loc` 指向哪个字段 | 对齐字段名与类型，并把校验失败纳入日志与监控 |
| 响应里出现内部备注、客户手机号 | 直接返回 ORM 对象或原始字典，未裁剪 | 对比 `response_model` 字段与表字段 | 显式定义响应模型，只放对外字段 |

## 安全与生产注意事项

**<u>把 `refund_id` 直接拼进 SQL 字符串，等于把分层省下的测试成本换成注入漏洞。</u>** 后果是攻击者可以读全表、改退款状态、绕过审核阈值。缓解办法：仓储层只用参数化查询；表名、排序字段走白名单；数据库账号只授予这张表需要的权限。

**<u>在模块顶层创建数据库会话或 HTTP 客户端，会在多 worker 下共享连接并串数据，配置缺失还会让整个应用无法导入。</u>** 缓解办法：用 `Depends` 加 `yield` 管理生命周期，连接池设上限与超时，启动时显式校验配置并给出可读报错。

**<u>生产环境暴露 `/docs`、`/openapi.json` 和详细的 `422` 报错，会把内部字段名与校验规则直接交给攻击者。</u>** 缓解办法：生产关闭文档路由或加鉴权；错误响应只返回稳定错误码；堆栈只进日志，不进响应体。

另外，不要把“当前用户 Token 原文”注入到服务层并打进日志。日志里只留用户标识和请求 ID，否则一次排障就会把凭据摊在日志平台里。

## 本课总结

- 接口层解析与翻译，服务层承载规则，仓储层封装存取，三层各自只有一个变化理由。
- **依赖注入让“谁创建依赖”从业务代码里消失**，对象只声明需要什么，于是同时获得可配置与可测试。
- 同一请求内同一依赖默认只求值一次，这正好对应“一个请求一个数据库会话”。
- 领域异常在边界上翻译，是同一套规则同时服务 HTTP、命令行和批处理的关键。
- 分层按变化频率切，不按文件数量切；只有几条增删改查的服务不值得四层。

## 思考题

退款服务既要给客服工作台调用，又要在对账批处理里复用同一套审核规则，还要按客户等级切换阈值。你会把“阈值选择”放在接口层、服务层，还是抽成独立的策略对象？请说明理由，并写出这个选择对测试和配置的要求。

参考思路：放接口层会让重复随入口数增长；把多套 `if` 塞进服务层深处，会让服务层承担渠道差异。抽成策略对象（按调用方与客户等级解析阈值）更易单测与配置化，但要求调用方显式传入上下文，而不是让服务层用全局状态去猜“现在是谁在调用”。

## 小测

1. 下列哪一项最该放在仓储层？  
   A. 判断退款金额是否超过审核阈值　B. 按主键查询退款并加行锁　C. 把领域异常转成 `404`　D. 校验请求体字段类型
2. 为什么不在模块顶层执行 `SETTINGS = Settings()` 读取环境变量？
3. 路由函数里写 `if amount > 50000: need_review = True`，主要问题是什么？
4. `Depends` 在同一个请求内对同一依赖默认求值几次？这对数据库会话意味着什么？
5. 场景题：同事说“服务层不该知道 HTTP，但 `404` 是业务语义，所以服务层可以直接 `raise HTTPException(404)`”。你同意吗？

## 答案与解析

1. **B。** A 是业务规则，应住服务层；C 是协议翻译，属于接口层或异常处理器；D 是框架的入参校验，也在接口层。仓储只回答“怎么存、怎么取、怎么加锁”。
2. 导入即求值会带来三个后果：测试无法替换配置；少一个环境变量是 `import` 崩溃而不是启动时报错；多环境共用同一份全局状态。应改用 `Depends` 工厂或显式初始化的单例，让配置在启动或请求边界上被构造，一次且可控。
3. 规则会随接口复制扩散：新增一个入口就要再抄一遍，阈值调整要改多处，而且无法脱离 HTTP 单测。应把判断移到服务层，接口层只负责调用。
4. 默认一次，同一请求内共享结果，这正好对应“一个请求一个数据库会话”，也保证并发请求之间不共享会话。前提是依赖内部不要写全局可变状态，否则这个假设立刻失效。
5. 不同意。`404` 是 HTTP 的表达，业务事实只是“这笔退款不存在”。服务层抛 `LookupError` 之类的领域异常，由接口层翻译成 `404`、由命令行入口翻译成退出码和日志，两边都不丢语义。直接在服务层 `raise HTTPException` 的结果是：测这条规则得先装 FastAPI。

### 动手实验参考

阈值改到 `15000` 后，`R-1`（19900 分）越过阈值，`next_action` 变成 `manual_review`；`R-2`（88000 分）不变。新增 `closed` 规则时，在 `decide` 里先判断 `row["status"] == "closed"` 直接返回 `manual_review`，其余逻辑不动。<u>这里最容易错的是单位：199 元是 19900 分，阈值 150 元是 15000 分，写成 `150` 会让所有退款都自动通过。</u>

## 延伸阅读与下一课

- FastAPI 官方文档《Dependencies》：`Depends` 的用法与依赖缓存机制，<https://fastapi.tiangolo.com/tutorial/dependencies/>。
- FastAPI 官方文档《Bigger Applications》：用 `APIRouter` 把项目拆成多个模块，<https://fastapi.tiangolo.com/tutorial/bigger-applications/>。
- FastAPI 官方文档《Testing Dependencies with Overrides》：测试期替换依赖，<https://fastapi.tiangolo.com/advanced/testing-dependencies/>。
- ASGI 规范：理解 Uvicorn 与应用对象之间的边界，<https://asgi.readthedocs.io/en/latest/>。

- 返回[本单元目录](00-overview.md)。
- 回看上一单元：[数据与应用架构](../05-data-and-architecture/00-overview.md)。
- 下一课：[依赖、虚拟环境、配置与 Secret](02-dependencies-config-and-secrets.md)。
