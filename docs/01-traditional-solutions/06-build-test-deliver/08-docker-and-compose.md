---
title: Docker 与 Docker Compose
slug: docker-and-compose
module: traditional-solutions
stage: deploy-and-deliver
type: core
difficulty: beginner
duration: 55m
prerequisites:
  - linux-processes-and-diagnostics
outcomes:
  - 解释镜像分层、容器可写层与卷在数据持久化上的差别
  - 用一份 compose.yaml 定义多服务、命名卷和健康检查，并按健康状态控制启动顺序
  - 判断“端口不通”“数据丢失”“改了代码不生效”分别出在网络、挂载还是构建缓存
last_reviewed: 2026-10-19
---

# Docker 与 Docker Compose

## 为什么需要学习

晴空商城的退款集成服务在开发同事的本机能跑通，到预发却起不来：那台机器没装 PostgreSQL，Redis 比开发机低两个大版本，运维照着“先装依赖再改配置”的 Wiki 操作了三小时。两周后客服要复现一个退款卡单，三个人各配了一套互不相同、都只“部分成功”的环境。

这些事故不是因为谁不会写代码，而是因为**应用的运行环境从未被当作交付物**。代码能提交、能评审、能回滚，环境却靠口口相传。

> **核心结论：** 镜像把“运行时 + 依赖 + 启动参数”固化成可复现、可回滚的交付物；Compose 把“一个服务”扩展成“一栈服务 + 网络 + 数据卷 + 启动顺序”。

## 学习目标

完成本课后，你能够：

- 说出镜像、容器、卷三者的生命周期差异，并判断一份数据该放进镜像、可写层还是卷。
- 按“变化频率从低到高”的顺序写 Dockerfile，并解释这样写为什么能命中构建缓存。
- 写出一份包含多服务、命名卷、健康检查和 `depends_on` 条件的 `compose.yaml`。
- 用 `docker compose ps`、`logs`、`inspect` 定位一次启动失败或端口不通。
- 判断一个场景该继续用 Compose 还是已需要 Kubernetes。

## 前置知识

- 回看上一课：[Linux、进程与诊断方法](07-linux-processes-and-diagnostics.md)。
- 会用 `ps`、`ss`、`tail -f` 观察一个服务，并解释“监听 `127.0.0.1`”与“监听 `0.0.0.0`”的差别。
- 读过[依赖、虚拟环境、配置与 Secret](02-dependencies-config-and-secrets.md)，知道环境变量与 Secret 的分层。

## 业务场景

退款集成服务进入交付阶段，需要同时满足三种使用方式：

- 开发同事在本机一键拉起 `refund-api`、PostgreSQL、Redis 和 Nginx，用于联调支付回调。
- 预发环境用**与生产完全相同的镜像**，只替换配置和 Secret，不再手工装软件。
- 客服与财务需要随时回看某一次退款为什么失败，因此必须能回答“当时跑的是哪个镜像版本”。

约束很具体：财务要求每次退款可追溯到镜像标签；安全要求容器不以 root 运行、密钥不进镜像；客服本机没有运维权限，只能执行一条命令。本课解决的是把“能运行的服务”变成“能交付的一栈”。

## 核心概念

*镜像*（image）是一个只读的、带元数据的文件系统快照，包含运行时、依赖和应用代码。*容器*（container）是镜像的一次运行实例，在只读层之上加一层*可写层*记录运行期的文件改动——**容器被删除时，可写层里的数据一起消失**。

*Dockerfile* 是构建镜像的指令清单，每条指令产生一个*层*（layer），层是不可变的，因此可以被上层复用。*构建缓存*指某条指令的输入与上次完全相同时直接复用旧层、跳过执行。

*卷*（volume）是由 Docker 管理的、独立于容器生命周期的存储，容器删了它还在。*绑定挂载*（bind mount）把宿主机上的一个目录直接映射进容器，内容由宿主机文件系统决定。

*容器网络*是每容器独立的网络命名空间，默认经 *bridge 网络*与宿主机通信。Compose 为整个项目建一个 bridge 网络，让*服务名*经内嵌 DNS 解析成容器 IP。

*Compose 项目*是由一个 `compose.yaml` 描述的一组服务、网络和卷，用一条命令统一启停。*健康检查*（healthcheck）是编排层周期性在容器内跑探针命令、判断“业务真能服务”的机制。

| 对象 | 谁创建 | 生命周期 | 适合放什么 | 晴空商城示例 |
| --- | --- | --- | --- | --- |
| 镜像层 | `docker build` | 永久，可被多个镜像共享 | 代码、依赖、系统库 | `python:3.12-slim` 基础层 |
| 容器可写层 | `docker run` | 随容器创建与删除 | 临时文件、运行时缓存 | 应用写的 `/tmp` 日志缓冲 |
| 命名卷 | Docker 守护进程 | 不随容器删除 | 需要跨重建保留的数据 | PostgreSQL 数据目录 |
| 绑定挂载 | 用户指定宿主机路径 | 由宿主机决定 | 本机开发时代码热更新 | 把 `./app` 挂进容器调试 |
| Secret | 部署平台注入 | 随实例 | 密钥、口令 | 支付 API Key |

<u>上表里没有“代码”和“日志”的位置</u>：代码应该进镜像层并随标签版本化，日志应该走标准输出交给日志驱动，而不是写进容器文件或卷里当数据保管。

## 工作原理

一次“从源码到一栈运行”的过程按以下顺序发生：

1. **构建**：`docker build` 逐条执行 Dockerfile。每条指令把“上一层 + 本层改动”打包成新层，并计算内容摘要作为缓存键。
2. **命中缓存**：摘要与已有层一致就复用。某条指令一旦变化，它**之后的所有层**全部失效。
3. **产出镜像**：镜像 = 只读层栈 + 元数据（`CMD`、`ENTRYPOINT`、`ENV`、`USER`、`EXPOSE`）。
4. **创建容器**：`docker run` 在只读层顶部加一个可写层，并创建独立的 PID、网络、挂载命名空间，把镜像的 `CMD` 作为 PID 1 启动。
5. **挂载存储**：卷和绑定挂载在创建容器时被挂进挂载命名空间，读写绕过可写层，因此能活过容器重建。
6. **接入网络**：Compose 建 bridge 网络、分配 IP，并把服务名注册进内嵌 DNS；同项目内 `db` 就能解析到数据库容器。
7. **发布端口**：`ports: "127.0.0.1:8080:8000"` 由宿主机端口转发到容器端口，宿主机在 `127.0.0.1:8080` 上监听。
8. **探活**：每 `interval` 在容器内执行 `test`，成功记 healthy；连续失败 `retries` 次记 unhealthy，`start_period` 内的失败不计。
9. **控制顺序**：`depends_on` 带 `condition: service_healthy` 时，Compose 等前置服务 healthy 才启动当前服务。
10. **停止**：`docker compose down` 按依赖反序发 `SIGTERM`，超时后 `SIGKILL`；卷只在显式加 `-v` 时删除。

请求路径可以简化为：客服浏览器 → 宿主机 `127.0.0.1:8080` → iptables 转发 → bridge 网络 → 容器 `eth0:8000` → 应用。这条链上任何一环没配好，表现都是“连不上”，但排查位置完全不同。

## 架构与选型

| 方案 | 适用场景 | 不适用场景 | 主要权衡 |
| --- | --- | --- | --- |
| 单条 `docker run` | 临时验证一个镜像、跑一次性工具 | 两个以上需要互联的服务 | 上手最快，但参数散落在脚本里，难以复现 |
| Docker Compose | 单机多服务、开发与预发环境、演示交付 | 需要跨多台机器调度、自动扩缩容、滚动更新 | 声明式、一条命令启停，但不做集群编排 |
| Kubernetes | 多团队、多节点、需要自愈与弹性 | 小团队单机部署、学习成本无法摊薄 | 能力强，但运维与认知成本高一个数量级 |
| 裸机 + `systemd` | 只有一个服务、机器已被托管 | 需要隔离依赖版本、需要频繁重建 | 无额外抽象，但环境漂移由人承担 |
| 托管 PaaS | 团队不想管运行时和主机 | 需要特权能力、自定义网络、特定内核参数 | 交付最省事，但可定制性受限 |

选型看三个量：服务数量、是否跨机器、发布频率。退款栈是单机四服务、每周发布一次、没有专职平台工程师，因此**选 Compose 而不是 Kubernetes**；等到需要多节点自愈和灰度时再升级（下一课）。

## 最小示例

**问题**：让退款服务、数据库和缓存在同一台机器上按正确顺序启动，并且数据不丢、端口只对本机开放。**环境**：Docker Engine 24 以上 + Docker Compose V2（命令是 `docker compose`，中间有空格）。**输入**：源码目录、`requirements.txt`。**输出**：一个可复制到预发的镜像版本，和一个能自检的服务栈。

第一步是镜像。指令顺序就是缓存策略：

```dockerfile
# 基础镜像锁到 minor 版本：latest 会在某次构建时悄悄换掉 Python 与系统库
FROM python:3.12-slim

# 进镜像元数据的运行约定：不生成 .pyc；日志不缓冲，docker logs 才能实时看到
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先只复制依赖清单：清单不变，下面最贵的一次安装就一直命中缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 再复制源码：源码几乎每次都变，放在依赖安装之后，才不会每次都重装依赖
COPY app ./app

# 创建非 root 用户并切换，降低容器内进程被利用后的影响面
RUN useradd --create-home --uid 10001 appuser
USER 10001

EXPOSE 8000

# exec 形式：PID 1 直接是 uvicorn，能收到 docker stop 的 SIGTERM 并优雅退出
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

第二步用 Compose 描述整栈：

```yaml
# 不写 version 字段：Compose V2 按规范解析，写了只会收到 “version is obsolete” 警告
name: qingkong-refund          # 项目名决定网络与容器名前缀，避免与同事本机其他栈冲突

services:
  refund-api:
    build: .                   # 用当前目录的 Dockerfile 构建
    image: qingkong/refund-api:2026.10.19   # 打可追溯标签，而不是 latest
    environment:
      DATABASE_URL: postgresql://refund:refund@db:5432/refund  # 主机名是服务名 db，不是 localhost
      REDIS_URL: redis://cache:6379/0
    ports:
      - "127.0.0.1:8080:8000"  # 只发布到回环地址：演示环境不把退款接口暴露到局域网
    depends_on:
      db:
        condition: service_healthy   # 等数据库能接受连接，而不是只等“容器已创建”
      cache:
        condition: service_healthy
    healthcheck:
      # 探针复用镜像里已有的 python3，不为一条检查命令再装 curl
      test: ["CMD", "python3", "-c", "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=2)"]
      interval: 10s
      timeout: 3s
      retries: 3
      start_period: 20s        # 启动期失败不计，给连接池和迁移热身

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: refund
      POSTGRES_PASSWORD: refund      # 仅本机演示；生产口令由 Secret 注入
      POSTGRES_DB: refund
    volumes:
      - refund-pgdata:/var/lib/postgresql/data   # 命名卷：容器删了数据还在
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U refund -d refund"]
      interval: 5s
      timeout: 3s
      retries: 10

  cache:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  refund-pgdata:               # 卷随项目命名；只有 down -v 才会删除
```

第三步是健康检查的判定逻辑本身。它在没有 Docker 的机器上也能跑，用来理解 `interval` 与 `retries` 到底做了什么：

```python
import sys                     # 用退出码表达健康判定，便于脚本化和流水线复用
import time                    # 控制两次探测之间的间隔
import urllib.error            # 区分“连不上”和“连上了但状态码不对”两类失败
import urllib.request          # 只用标准库，避免依赖镜像里可能不存在的 curl


def probe(url, expected=200):
    """探测一次，返回 (是否健康, 可读结论)。"""
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == expected, f"{response.status} {response.reason}"
    except urllib.error.HTTPError as error:            # 连上了但状态不对：进程在，业务未就绪
        return False, f"{error.code} {error.reason}"
    except (urllib.error.URLError, OSError) as error:  # 连不上：未监听、端口未发布或被网络隔离
        return False, f"连接失败（{error.__class__.__name__}）"


def wait_healthy(url, budget_seconds, interval=1.0):
    """在总预算内重试，模拟 interval / retries 语义。"""
    deadline = time.monotonic() + budget_seconds
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        ok, detail = probe(url)
        print(f"第 {attempt} 次探测: {detail}")  # 每次都打印，便于和容器日志对照
        if ok:
            return 0
        time.sleep(interval)
    return 1                                     # 预算耗尽仍未健康，交给编排层判失败


if __name__ == "__main__":
    target = sys.argv[1]                              # 例如 http://127.0.0.1:8080/healthz
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 10
    raise SystemExit(wait_healthy(target, budget))
```

用标准库起一个只有 `/healthz` 返回 200 的小服务后运行它，以下是本地实测输出：

```bash
$ python3 wait_healthy.py http://127.0.0.1:8123/healthz 5
第 1 次探测: 200 OK                      # 退出码 0

$ python3 wait_healthy.py http://127.0.0.1:8123/ 2
第 1 次探测: 404 Not Found
第 2 次探测: 404 Not Found               # 退出码 1，进程活着但路径错，典型的探针配错

$ python3 wait_healthy.py http://127.0.0.1:8123/healthz 3
第 1 次探测: 连接失败（TimeoutError）     # 退出码 1，服务未监听或端口未发布
```

整体流程是：Dockerfile 先固化依赖再固化源码 → Compose 建网络与卷 → 数据库和缓存先起并被探活 → `refund-api` 在依赖 healthy 后启动 → 应用自身的 `/healthz` 被周期探测。三处选择值得记住：依赖清单先复制，缓存才不被源码变更击穿；探针只用镜像内已有工具；数据库固定用命名卷，数据去留由人决定。

构建与启动命令，`docker compose` 的输出为预期输出（版本不同文案略有差异）：

```bash
$ docker compose up -d --build
[+] Building 41.2s (11/11) FINISHED
[+] Running 4/4
 ✔ Network qingkong-refund_default  Created
 ✔ Container qingkong-refund-db-1    Healthy
 ✔ Container qingkong-refund-cache-1 Healthy
 ✔ Container qingkong-refund-api-1   Started        # 注意它是最后起的

$ docker compose ps
NAME                       SERVICE     STATUS                    PORTS
qingkong-refund-api-1      refund-api  Up 12 seconds (healthy)   127.0.0.1:8080->8000/tcp
qingkong-refund-cache-1    cache       Up 25 seconds (healthy)   6379/tcp
qingkong-refund-db-1       db          Up 25 seconds (healthy)   5432/tcp
```

## 动手实验

**前置条件**：本机装好 Docker Engine 或 Docker Desktop，`docker compose version` 能打印 V2 版本；一个可写目录；示例 `Dockerfile`、`compose.yaml`、`wait_healthy.py` 已保存到该目录（`app/` 与 `requirements.txt` 可用一个返回 `/healthz` 的最小服务代替）。

1. 构建并后台启动整栈：`docker compose up -d --build`。
2. 观察启动顺序，确认 `refund-api` 在 `db` 之后进入 healthy：

   ```bash
   docker compose ps
   docker compose logs --tail=20 db
   ```

3. 从宿主机验证端口只对本机开放：

   ```bash
   python3 wait_healthy.py http://127.0.0.1:8080/healthz 20
   curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/healthz
   ```

4. 验证数据卷跨容器重建存活：

   ```bash
   docker compose exec db psql -U refund -d refund -c "create table probe(id int);"
   docker compose restart db
   docker compose exec db psql -U refund -d refund -c "\dt"
   ```

5. 验证容器内用户不是 root，且服务名可解析：

   ```bash
   docker compose exec refund-api id -u
   docker compose exec refund-api python3 -c "import socket; print(socket.gethostbyname('db'))"
   ```

预期结果：第 2 步三行状态最终都含 `healthy`，`db` 与 `cache` 的启动时间早于 `refund-api`；第 3 步 `wait_healthy.py` 打印 `200 OK` 并退出 0，`curl` 输出 `200`；第 4 步重启后 `\dt` 仍能列出 `probe` 表；第 5 步 `id -u` 输出 `10001`（不是 `0`），域名解析返回一个 `172.x` 地址。

验证方法：状态、退出码、表是否存在、UID 是否非零，四项都是可机读证据；任一项不符就按下一节的表格定位。

清理方法：`docker compose down -v` 停止并删除容器、网络和命名卷；再执行 `docker image rm qingkong/refund-api:2026.10.19` 删除本次构建的镜像。若想保留数据排查，先执行不带 `-v` 的 `docker compose down`。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 容器启动即退出，`ps` 里看不到 | `CMD` 被写成 shell 形式并加了 `&`，或应用读完参数就返回 | `docker compose ps -a` 看退出码，`logs` 看最后一行 | 改 exec 形式 `CMD`，让主进程留在前台 |
| 改了代码，容器里还是旧行为 | 没重建镜像，缓存命中了旧的 `COPY app` 层 | `build --no-cache` 后重试；`image inspect -f '{{.Created}}'` | 加 `--build`；本机开发可临时绑定挂载 |
| 宿主机访问 `localhost:8080` 不通 | 服务监听 `127.0.0.1` 而不是 `0.0.0.0`，或 `ports` 只写了容器端口 | `docker compose port refund-api 8000`；`ss -ltnp` 看宿主机是否有监听 | 应用改为监听 `0.0.0.0`；确认 `ports` 是 `宿主机:容器` |
| 容器内连数据库报“连接被拒绝” | 用了 `localhost`，而 `localhost` 指的是容器自己 | `docker compose exec refund-api getent hosts db` | 连接串主机名改成服务名 `db` |
| 健康检查一直是 `unhealthy` | 探针命令在镜像里不存在（如没装 `curl`），或路径写成 `/health` 而应用只有 `/healthz` | `docker inspect -f '{{json .State.Health}}' <容器>` 看每次输出 | 换成镜像内已有工具；探针路径与应用实际路由对齐 |
| `depends_on` 写了但启动顺序没变 | 用了列表简写，只保证启动先后，不保证可用 | 查看 compose 文件里是否有 `condition:` | 改成 `condition: service_healthy`，并确保被依赖服务有健康检查 |
| `down` 之后数据全没了 | 数据目录写在可写层，或用了 `down -v` | `docker volume ls` 看卷是否还在 | 数据目录改挂命名卷 |

## 安全与生产注意事项

**<u>不要把宿主机的 Docker socket 挂进容器</u>**（`/var/run/docker.sock:/var/run/docker.sock`）。能访问它的进程等同拥有宿主机 root：可以创建特权容器、挂载宿主机根文件系统、读取所有容器的环境变量，单点沦陷就变整机沦陷。缓解办法是让需要编排能力的组件直接跑在宿主机上，或改用只读代理。

**<u>不要把密钥写进 Dockerfile 或镜像里，即使“后面再删除”</u>**。`RUN export TOKEN=...` 或先 `COPY .env` 再 `RUN rm .env` 都会把值留在历史层中，任何能拉取镜像的人都能用 `docker history` 或解层工具取出。缓解办法是构建期用 BuildKit 的 secret 挂载、运行期由平台注入环境变量或只读文件，并且用 `.dockerignore` 挡住 `.env`、`.git`。

**<u>不要用 `latest` 标签部署，也不要长期以 root 运行容器</u>**。`latest` 让回滚没有确定落点，发布失败两次就说不清线上是哪一版；root 容器被利用时直接影响面是宿主机。缓解办法是打不可变标签（提交哈希或日期版本），并在 Dockerfile 里 `USER` 切到非 root。

另外两条约定：给所有服务写 `healthcheck`，否则编排层只能判断“进程在”；把 `restart: unless-stopped` 与 `mem_limit` 等限制写进 Compose，避免一个服务打满内存连累全栈。

## 本课总结

- **镜像是可复现的交付物**：层不可变、内容决定缓存键，指令顺序直接决定构建速度。
- **容器可写层随时消失**：需要留下的数据必须放命名卷，需要热更新的代码才用绑定挂载。
- **容器网络里 `localhost` 是容器自己**：跨服务用服务名，对外发布端口要写 `宿主机:容器`。
- **健康检查把“进程启动”升级为“业务可用”**，配合 `condition: service_healthy` 才真正控制启动顺序。
- **Compose 是单机编排的正确工具**：服务数量、跨机器需求、发布频率决定何时升级到 Kubernetes。

## 思考题

上线半年后，业务要求“发布不中断支付回调，且 5 分钟内能回滚”。请说明这套 Compose 栈已提供哪些能力、必须补哪些，以及你会把 Compose 留在什么位置。

参考思路：先拆需求——“不中断”要副本与流量切换，“5 分钟回滚”要不可变标签和可重复的启动路径。Compose 能提供后者与健康门禁，但不提供跨机器调度、滚动替换和自动回滚。可行路径是 Compose 留在开发与预发，生产侧引入具备滚动更新能力的平台或反向代理灰度，并把镜像标签、健康检查、迁移脚本做成两侧共用的事实来源。

## 小测

1. 容器里写入 `/app/data.json`，容器删除后该文件会怎样？为什么？
2. 下列哪种改动会击穿后续所有层的构建缓存？  
   A. 修改 `app/main.py`　B. 修改 `requirements.txt`　C. 修改 `healthcheck` 间隔　D. 修改 `ports` 映射
3. 同一个 Compose 项目里，`refund-api` 应该用什么主机名连 PostgreSQL？为什么不能用 `localhost`？
4. 健康检查一直显示 `unhealthy`，但容器里手动执行应用命令是正常的，最可能的原因是什么？
5. 场景题：同事说“`depends_on` 已经写了，为什么应用启动时还是报数据库连接失败？”请给出判断依据和修复方向。

## 答案与解析

1. 文件随容器一起消失。它写在可写层，可写层与容器同生命周期。要让文件跨容器重建保留，应把该路径挂到命名卷；要让它随镜像分发，应在构建阶段写入镜像层。
2. **B。**`requirements.txt` 被 `COPY` 之后紧跟 `RUN pip install`，改动它会让这一层及其后所有层失效，包括源码复制。A 只影响最后一个 `COPY app` 层；C 和 D 属于 Compose 的运行期配置，根本不参与镜像构建。
3. 用服务名 `db`（与 `compose.yaml` 里的键一致）。每个容器有独立网络命名空间，容器内的 `localhost` 指向容器自身，而 Compose 的内嵌 DNS 会把服务名解析成对应容器的 IP。这也是“本机能连、容器里连不上”的最常见原因。
4. 探针命令在容器内不可用或目标不对。典型是镜像里没装 `curl` 却写了 `curl -f http://localhost:8000/healthz`，或路径写成 `/health` 而应用只有 `/healthz`。<u>手动执行成功不等于探针成功</u>——两者的 shell、PATH 和参数可能不同。
5. 看 `depends_on` 的写法：列表简写只保证“先启动”，不保证“可接受连接”，数据库从启动到能响应查询还有一段时间。修复是给被依赖服务加 `healthcheck`，把 `depends_on` 改成 `condition: service_healthy`；应用侧仍保留连接重试，别把编排顺序当唯一保障。

### 动手实验参考

第 2 步 `db` 与 `cache` 的 `Up` 时间应早于 `refund-api`，`logs db` 里能看到 `database system is ready to accept connections`；第 3 步应打印 `200 OK` 并退出 0，一直打印 `连接失败` 就先查 `ports` 与监听地址；第 4 步 `\dt` 仍列出 `probe` 表，否则挂载路径不是 `PGDATA` 目录；第 5 步 `id -u` 非零才说明 `USER` 生效。

## 延伸阅读与下一课

- [Docker 官方文档：构建最佳实践](https://docs.docker.com/build/building/best-practices/) 解释层缓存顺序与非 root 用户的推荐写法。
- [Docker 官方文档：Compose 文件参考](https://docs.docker.com/compose/compose-file/) 是 `healthcheck`、`depends_on` 等字段的权威定义。
- [Docker 官方文档：在 Compose 中控制启动顺序](https://docs.docker.com/compose/how-tos/startup-order/) 说明健康检查与 `condition` 如何决定启动先后。
- [Docker 官方文档：卷](https://docs.docker.com/storage/volumes/) 对比卷与绑定挂载的生命周期。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[Linux、进程与诊断方法](07-linux-processes-and-diagnostics.md)。
- 下一课：[CI/CD、变更、灰度与回滚](09-cicd-migrations-canary-and-rollback.md)。
