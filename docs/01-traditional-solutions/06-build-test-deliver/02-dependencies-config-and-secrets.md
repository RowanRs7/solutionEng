---
title: 依赖、虚拟环境、配置与 Secret
slug: dependencies-config-and-secrets
module: traditional-solutions
stage: build-and-integrate
type: core
difficulty: beginner
duration: 50m
prerequisites:
  - fastapi-service-and-layering
outcomes:
  - 为一个 Python 服务生成可复现的依赖锁定文件，并说明锁定文件与约束文件的区别
  - 创建独立虚拟环境，并用一条命令证明依赖安装在环境内而非系统解释器中
  - 按默认值、环境变量、Secret 三层写出配置加载顺序，并让服务在缺少 Secret 时启动即失败
last_reviewed: 2026-10-19
---

# 依赖、虚拟环境、配置与 Secret

## 为什么需要学习

晴空商城的退款集成服务上线第三天，客服发现所有自动退款都进了支付商的沙箱环境：测试环境能跑通，生产环境却把真实订单号发给了假接口。同一周，开发同事为了排查问题，把一段包含 `PAYMENT_API_KEY` 的启动日志贴进了工单群；两个月后团队重建镜像，支付 SDK 自动升了一个大版本，退款金额的精度处理变了，对账出现 3 分钱误差。

这三个事故的共同点是：代码没有错，**环境与配置没有被当作交付物管理**。

> **核心结论：** 依赖锁定保证“同一份代码在任何机器上装出同样的库”，配置分层保证“同一份镜像在任何环境里读对参数”，Secret 注入保证“密钥只在运行时存在、只出现在该出现的地方”。

## 学习目标

完成本课后，你能够：

- 生成并提交一份可复现安装的依赖锁定文件，说明它与约束文件的区别。
- 用 `venv` 建立隔离环境，并验证 `pip install` 的落点在环境内而不是系统 Python。
- 按“默认值 → 环境变量 → Secret 注入”的顺序解释配置的合并过程。
- 写出启动时校验必需配置的代码，让缺失密钥变成退出码而不是运行期 500。
- 判断一处配置该放代码、环境变量还是 Secret 管理器。

## 前置知识

- 回看上一课：[FastAPI 最小服务与项目分层](01-fastapi-service-and-layering.md)。
- 能在终端执行 `python3`、`pip`，知道包管理器会从索引下载并安装库。
- 知道 HTTP 服务启动时会读取端口、数据库地址一类的参数。
- 理解环境变量是进程启动时由父进程传入的键值对，子进程可继承。

## 业务场景

退款集成服务要同时存在三个环境：开发（本机连沙箱支付）、预发（连沙箱支付、用生产数据库副本）、生产（连真实支付）。三个环境的**代码必须是同一份**，差异只允许出现在配置里：

- 支付商 SDK 必须锁定版本。退款涉及金额与幂等，SDK 的补丁版本都可能改重试语义。
- 自动退款阈值 `REFUND_MAX_AUTO_AMOUNT` 在生产是 500 元，在开发和预发是 1 元，便于测试人工审核分支。
- 支付商 API Key、数据库口令、回调签名密钥属于 Secret，必须能独立轮换，且不能出现在镜像、仓库、日志里。
- 财务要求：任何一次退款请求都能追溯到“当时用的是哪个 SDK 版本、哪个环境、哪版配置”。

## 核心概念

*依赖*是代码运行需要的外部库。直接写在清单里的是*直接依赖*；它们自身要求的库是*传递依赖*。*依赖锁定*指把解析后的完整版本集合（含传递依赖及其校验和）写进文件，使安装结果可复现。

*虚拟环境*是一个装了独立解释器与 `site-packages` 的目录，让项目依赖与系统 Python 互不污染。*配置*是随环境变化、但不必改代码的参数；*Secret* 是配置中泄露即造成损失的那一类，例如密钥、口令、令牌。

*配置分层*是把配置按“默认值 → 环境文件 → 环境变量 → Secret 存储”排成优先级序列的约定。*Secret 注入*指在部署时由平台把 Secret 以环境变量或挂载文件的形式放进运行实例，而不是随代码分发。

| 概念 | 是否进代码仓库 | 是否进镜像 | 谁能读 | 晴空商城示例 |
| --- | --- | --- | --- | --- |
| 依赖清单与锁定文件 | 是 | 是 | 全员 | `requirements.txt`、`requirements.lock` |
| 代码内默认值 | 是 | 是 | 全员 | 超时 5 秒、日志级别 `info` |
| 环境变量（非敏感） | 否，写入部署描述 | 否 | 运维与开发 | `APP_ENV=prod`、`REFUND_MAX_AUTO_AMOUNT=500` |
| Secret | 否 | 否 | 运行时进程与授权运维 | `PAYMENT_API_KEY`、`DB_PASSWORD` |
| 本地开发 `.env` | 否（进 `.gitignore`） | 否 | 本机开发者 | 沙箱 Key，只用于本地 |

**锁定文件记录的是“解析结果”，约束文件记录的是“允许范围”。** 前者保证复现，后者只缩小求解空间，不能替代锁定。

## 工作原理

一次“从提交到生产可用”的配置生命周期按以下顺序发生：

1. **声明**：开发者在 `requirements.in` 里只写直接依赖和允许的版本范围，例如 `httpx>=0.27,<0.28`。
2. **求解**：`pip-compile` 解析出完整依赖树，把直接与传递依赖的精确版本写入 `requirements.lock`，并可用 `--generate-hashes` 附上校验和。
3. **隔离安装**：`python3 -m venv .venv` 创建环境，用 `.venv/bin/python -m pip install -r requirements.lock` 安装。CI 与生产构建执行同一条命令。
4. **构建镜像**：镜像里固化锁定文件与代码，不包含任何环境专属值，因此同一个镜像可以被三个环境引用。
5. **部署时注入**：平台读取环境描述里的非敏感变量，再从 Secret 管理器取密钥，以环境变量或只读文件挂进容器。
6. **进程启动读取**：应用按优先级合并配置——代码默认值被环境变量覆盖，Secret 从注入通道读取，不写入磁盘。
7. **启动校验**：缺必需项或类型不合法时立刻记录（不含值）并退出非零码，让部署失败而不是带病运行。
8. **运行期使用**：业务代码只依赖一个已校验的配置对象，不散落 `os.environ[...]`。
9. **轮换**：Secret 在管理器里更新，平台重启或滚动实例，旧值随之失效。

关键在于顺序：**越靠后的层覆盖越靠前的层，越靠后的层也越不该进版本库**。第 7 步是整条链路的保险丝，它把“配置错误”从线上 500 转换为部署失败。

## 架构与选型

| 方案 | 适用场景 | 不适用场景 | 主要权衡 |
| --- | --- | --- | --- |
| `venv` + `pip` + 锁定文件 | 单服务、Python 单一运行时、CI 简单 | 需要跨语言或多 Python 版本并行 | 简单透明，但需自己维护锁定流程 |
| Poetry / uv 等带锁文件工具 | 团队希望声明、锁定、安装一体化 | 生产构建已由镜像流水线统一管版本 | 命令更省事，但引入工具自身版本约束 |
| 容器镜像固化依赖 | 需要把运行时、依赖、系统库一起交付 | 依赖必须热更新且无法重建镜像 | 最可复现，但镜像体积与构建时间上升 |
| `.env` 文件 | 本机开发、一次性演示 | 生产、预发、任何共享环境 | 上手最快，最容易被误提交与误用 |
| 平台环境变量 | 12-Factor 风格多数服务的默认选择 | 需要结构化多段配置、密钥量很大 | 简单通用，但长文本与嵌套结构难表达 |
| Secret 管理器（云厂商服务、Vault、KMS） | 有多环境、轮换、审计要求的系统 | 单机本地练习、无外部依赖的离线演示 | 审计与轮换能力强，但引入外部依赖与启动时序 |

选型依据是三项事实：环境数量、密钥轮换频率、审计要求。晴空商城退款服务三项都高，因此选“镜像固化依赖 + 平台环境变量 + Secret 管理器”，`.env` 只保留在本机。

## 最小示例

下面的脚本用 Python 标准库演示分层读取、启动校验与脱敏输出。环境：Python 3.9 以上；输入是进程环境变量；输出是一份可安全打印的生效配置。

```python
import json          # 仅用于把最终生效的配置打印成可读 JSON
import os            # 环境变量是容器与 CI 中注入配置的通用通道
import sys           # 校验失败时用非零退出码让部署流水线立刻停下

# 第一层：代码内默认值。只允许放非敏感、跨环境相同的值。
DEFAULTS = {
    "APP_ENV": "dev",
    "PAYMENT_BASE_URL": "https://sandbox.pay.example.com",
    "REFUND_MAX_AUTO_AMOUNT": "500",
    "LOG_LEVEL": "info",
}

# Secret 键名清单。只有键名进代码，值永远由平台注入。
REQUIRED_SECRETS = ("PAYMENT_API_KEY",)


def load_config(environ):
    cfg = {}
    for key, default in DEFAULTS.items():
        cfg[key] = environ.get(key, default)   # 环境变量优先，缺失才回落默认值
    # 立刻转成数字，避免下游出现 "500" < 1000 这类字符串比较错误
    cfg["REFUND_MAX_AUTO_AMOUNT"] = int(cfg["REFUND_MAX_AUTO_AMOUNT"])
    return cfg


def require_secrets(environ):
    missing = [key for key in REQUIRED_SECRETS if not environ.get(key)]
    if missing:
        # 失败信息只报键名，绝不回显键值
        print(f"配置校验失败，缺少 Secret: {', '.join(missing)}", file=sys.stderr)
        raise SystemExit(2)
    return {key: environ[key] for key in REQUIRED_SECRETS}


def mask(value):
    # 只留后 4 位供运维核对，短值整体打码
    return "***" if len(value) <= 8 else f"***{value[-4:]}"


def main():
    secrets = require_secrets(os.environ)      # 先校验，再组装业务配置
    cfg = load_config(os.environ)
    cfg["PAYMENT_API_KEY"] = mask(secrets["PAYMENT_API_KEY"])  # 打印前脱敏
    print(json.dumps(cfg, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

运行方式与预期输出：

```bash
$ PAYMENT_API_KEY=sk_test_1234567890 python3 app_config.py
{
  "APP_ENV": "dev",
  "LOG_LEVEL": "info",
  "PAYMENT_API_KEY": "***7890",
  "PAYMENT_BASE_URL": "https://sandbox.pay.example.com",
  "REFUND_MAX_AUTO_AMOUNT": 500
}
$ python3 app_config.py; echo "退出码=$?"
配置校验失败，缺少 Secret: PAYMENT_API_KEY
退出码=2
```

设计要点：`DEFAULTS` 只放非敏感值，进仓库不会泄露；`REQUIRED_SECRETS` 只放键名，与默认值分开，使“Secret 不能有默认值”成为结构性约束；`mask` 让自检输出可以进工单而不制造二次泄露。

## 动手实验

**前置条件**：本机有 `python3`（3.9+）与可用的 `pip`；有一个可写的临时目录；示例脚本已保存为 `app_config.py`。

1. 建立隔离环境并确认落点：

   ```bash
   python3 -m venv .venv
   .venv/bin/python -c "import sys; print(sys.prefix != sys.base_prefix)"
   .venv/bin/python -m pip --version
   ```

2. 写一份只含直接依赖的 `requirements.in`，例如 `httpx>=0.27,<0.28`，再生成锁定文件：

   ```bash
   .venv/bin/python -m pip install pip-tools
   .venv/bin/python -m piptools compile requirements.in --output-file requirements.lock
   ```

3. 删除环境后按锁定文件重装，验证版本与第一次一致：

   ```bash
   rm -rf .venv && python3 -m venv .venv
   .venv/bin/python -m pip install -r requirements.lock
   .venv/bin/python -m pip freeze | grep -i httpx
   ```

4. 用示例脚本验证配置分层：分别在不设置、设置 `APP_ENV=prod`、设置 `REFUND_MAX_AUTO_AMOUNT=1` 三种情况下运行，观察输出差异；再删除 `PAYMENT_API_KEY`，确认退出码为 2。

**预期结果**：第 1 步输出 `True` 与 `.venv` 内的 `pip` 路径；第 3 步两次 `httpx` 版本完全相同；第 4 步输出随环境变量变化，缺 Secret 时只有一行不含密钥的报错。

**验证方法**：`pip check` 无冲突；`git status` 中不出现 `.env` 与 `.venv`；把输出贴给别人看时不含密钥原文。

**清理方法**：`deactivate`（若已激活）、`rm -rf .venv requirements.lock`，并删除本机测试用的环境变量。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| 本地可用，CI 或镜像内报 `ImportError` | 未锁定依赖，解析出新版本；或装进了系统解释器 | `python -c "import sys; print(sys.executable)"` 对比路径；比较 `pip freeze` 与锁定文件 | 提交锁定文件，构建时只用 `-r requirements.lock` |
| 生产仍连沙箱支付 | 默认值被当成生产值；环境变量未注入或拼错键名 | 启动日志打印 `APP_ENV` 与 `PAYMENT_BASE_URL`；在容器内执行 `env` 过滤键名 | 生产不设默认 URL，启动时强制校验该键非空 |
| 改了环境变量但服务行为不变 | 进程仍在运行，配置只在启动时读一次 | 比较配置生效时间与进程启动时间 | 重启或滚动实例；需要热更新时改用配置中心并加校验 |
| 密钥出现在日志或异常堆栈 | 直接打印整个配置对象或 `os.environ` | 在日志系统里按密钥前缀检索 | 只打键名与脱敏值；统一用白名单序列化 |
| `pip install` 报依赖冲突 | 手工改锁定文件或混装两个来源 | `pip check`、`pip install --dry-run` | 改 `requirements.in` 后重新编译，不手改锁定文件 |
| 预发与生产配置漂移无人发现 | 配置无版本、无评审 | 对比两环境导出的键名清单 | 配置纳入部署描述并做评审，Secret 只存值不存结构 |

## 安全与生产注意事项

**<u>Secret 一旦进入 Git 历史，就应视为永久泄露，而不仅是删除那一行。</u>** 后果是任何有仓库读权限的人（含镜像、缓存、fork）都能取到支付密钥；缓解办法是立即在支付商侧轮换密钥、改用 Secret 管理器注入、用扫描工具检查历史，并把 `.env` 加入 `.gitignore` 作为最低要求。

**<u>不要把 Secret 写进镜像、日志、异常信息或健康检查返回体。</u>** 镜像会被推送到多个仓库并被大量节点拉取，日志会被转发到第三方平台；缓解办法是只在运行时注入、统一脱敏函数、健康检查只返回 `ok` 与版本号，并限制 Secret 的读取权限与审计。

Secret 还要有负责人和轮换周期，非敏感配置也要经过评审并记入部署描述，否则环境漂移会长期潜伏。

## 本课总结

- 可复现的安装来自**锁定文件**，它记录解析结果；约束文件只限定范围。
- 虚拟环境把项目依赖与系统解释器隔离，构建与 CI 必须使用同一个解释器路径。
- 配置按“代码默认值 → 环境变量 → Secret 注入”分层，后层覆盖前层。
- Secret 只在运行时存在，代码和日志里只允许出现键名与脱敏值。
- 启动时校验必需配置，让配置错误变成部署失败，而不是线上 500。

## 思考题

退款服务的支付商 Key 需要每 90 天轮换一次，而服务有 8 个实例、滚动发布需要 5 分钟。你会怎样设计轮换流程，使这段时间既不产生退款失败，也不出现两套凭据长期并存？请说明你接受的风险和需要监控的信号。

参考思路：可考虑“新旧双 Key 并存窗口 + 按比例灰度 + 失败回退”的方案：先在支付商侧生成新 Key 并保持旧 Key 有效，把新 Key 写入 Secret 管理器，滚动重启实例使部分实例先用新 Key，观察退款成功率与签名失败指标，全部切换后再吊销旧 Key。需要说明的风险是并存窗口延长了泄露面，因此要限制窗口时长、记录每次使用哪一版凭据，并设置签名失败率告警。

## 小测

1. 锁定文件与约束文件的核心区别是什么？
2. 下列哪一项**不应**写进代码仓库？  
   A. `requirements.lock`　B. 日志级别默认值　C. 生产数据库口令　D. 依赖清单
3. 为什么说“Secret 不应该有代码内默认值”？
4. 配置在进程生命周期中的读取时机通常是什么？这对修改配置有什么影响？
5. 场景题：同事说“我把 `.env` 提交上去，方便新同学一键启动”。你应该同意吗？请说明理由与替代方案。

## 答案与解析

1. 锁定文件记录一次解析后的精确版本（可含校验和），重装结果可复现；约束文件只写版本范围，用来缩小求解空间，安装结果仍可能变化。
2. **C。**口令是 Secret，必须由运行时注入。A 与 D 是复现安装的依据，必须进仓库；B 是非敏感默认值，进仓库便于统一行为。
3. 有默认值意味着“缺 Secret 也能启动”，缺失或注入失败会被默认值掩盖，服务可能带着错误凭据连接沙箱或旧账号；把它设为必需并启动即失败，才能暴露注入链路问题。
4. 多数服务在进程启动时读取一次并保存在内存中。因此修改环境变量后必须重启或滚动实例才生效；如果需要热更新，就要引入配置中心，并为变更加校验与回滚。
5. 不应同意。`.env` 一旦提交即进入历史，任何有读权限的人都能取得其中的密钥，且后续删除无法消除泄露。替代方案是提交 `.env.example`，只列键名与说明，值由本机自行填写并加入 `.gitignore`；共享环境改用平台环境变量与 Secret 管理器。

### 动手实验参考

第 1 步输出 `True` 说明当前解释器不属于系统 Python，`pip --version` 路径应包含 `.venv`；第 3 步两次 `httpx` 版本应完全一致，若不一致说明没有真正使用锁定文件；第 4 步中 `APP_ENV=prod` 应覆盖默认值，`REFUND_MAX_AUTO_AMOUNT=1` 应输出数字 `1` 而非字符串，缺 Key 时退出码为 `2` 且 stdout 无内容。

## 延伸阅读与下一课

- [The Twelve-Factor App：Config](https://12factor.net/config) 给出“配置存于环境”的原始论证。
- [Python 官方文档：venv](https://docs.python.org/3/library/venv.html) 说明虚拟环境的创建与隔离边界。
- [pip 文档：约束文件](https://pip.pypa.io/en/stable/user_guide/#constraints-files) 解释 constraints 与 requirements 的差别。
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) 覆盖存储、注入、轮换与审计的检查项。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[FastAPI 最小服务与项目分层](01-fastapi-service-and-layering.md)。
- 下一课：[异常处理与结构化日志](03-exception-handling-and-structured-logging.md)。
