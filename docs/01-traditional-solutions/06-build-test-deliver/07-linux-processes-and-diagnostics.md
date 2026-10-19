---
title: Linux、进程与诊断方法
slug: linux-processes-and-diagnostics
module: traditional-solutions
stage: operate-and-optimize
type: core
difficulty: beginner
duration: 50m
prerequisites:
  - performance-security-and-data-testing
outcomes:
  - 用 ps、pgrep、systemctl status 判断服务进程是否存在、是否在反复重启
  - 用 ss、lsof 区分"进程没起来"和"进程在跑但端口没被监听"，并说明绑定地址决定了谁能访问
  - 为"服务不可用""接口变慢""磁盘将满"三类现象各写出三步之内的命令组合
last_reviewed: 2026-10-19
---

# Linux、进程与诊断方法

## 为什么需要学习

晴空商城的退款任务服务上线第二周，客服反馈"退款受理页一直转圈"。值班同学在群里问"是不是数据库挂了"，二十分钟里四个人分别猜了数据库、网络、支付商和前端，没人登录过那台机器。真实原因是昨天扩容后日志目录写满，`refund-worker` 被内核的 *OOM killer*（内存耗尽时强杀进程的机制）杀掉，重启策略又把它拉起；新进程绑定端口失败，于是一直反复重启。

诊断能力的差距不在"知道多少命令"，而在**知道按什么顺序看、每一步在排除哪个假设**。命令是手臂，顺序才是方法。

> **核心结论：** 排障效率取决于把"可能的原因"收敛成"已被证据排除的原因"的速度，而不取决于命令背了多少条。

## 学习目标

完成本课后，你能够：

- 用 `ps`、`pgrep`、`systemctl status` 判断一个服务进程是否存在、是否在反复重启，并读出它的 PID 与运行时长。
- 用 `ss`、`lsof` 区分"进程没起来"和"进程在跑但端口没被监听"这两种不同故障。
- 按 CPU、内存、磁盘（含 inode）、文件描述符四类资源各选一条命令，并说明它读的是哪个数据源。
- 用 `journalctl` 与 `tail`、`grep` 在给定时间窗口内定位一条错误的上下文。

## 前置知识

- 回看上一课：[性能、安全与数据质量测试](06-performance-security-and-data-testing.md)。
- 能在终端执行命令，理解管道 `|` 把上一个命令的输出交给下一个命令。
- 知道 HTTP 服务需要占用一个端口，客户端通过 IP 加端口访问它。
- 知道日志是程序写到文件或标准输出的文本记录。

## 业务场景

晴空商城的退款集成服务 `refund-worker` 以单机进程方式运行在一台 4 核 8 GB 的 Linux 虚拟机上（尚未容器化，容器是下一课）。它对外暴露 8080 供客服后台调用，对内每 30 秒轮询一次支付商的退款结果。

这一周它出了三次事故，客服侧看到的现象完全一样——"退款页面转圈"：

| 时间 | 客服看到的现象 | 实际原因 |
| --- | --- | --- |
| 周一 | 全部退款请求超时 | 进程被 OOM killer 杀掉，重启策略正在拉起，端口无人监听 |
| 周三 | 只有新退款排队变慢 | 磁盘剩余 2%，日志写入阻塞 |
| 周五 | 部分请求 502 | 进程只监听了 `127.0.0.1`，负载均衡探活失败 |

三种事故的外部表现一致，只能靠机器上的证据区分。本课练的就是**从同一症状出发，用命令把三条原因路径分开**。

## 核心概念

*进程*是一个运行中程序的实例，拥有独立的 *PID*（进程标识符）、内存空间和已打开的文件。同一个程序可以启动多次，得到多个互不相同的 PID。*端口*是 TCP/UDP 用来区分同一 IP 上不同服务的数字；进程要接收请求，必须先*监听*某个"地址加端口"的组合。

*监听*是进程向内核登记"发往这个端口的连接请交给我"。它和"进程存在"是两件事：进程活着但绑定失败时会一直重试，此时端口没有主人。

*文件描述符*是进程打开文件、套接字或管道时拿到的整数句柄，数量有上限（`ulimit -n`）。句柄泄漏的典型表现是进程活着、CPU 不高，但新连接全部失败。

*负载*是内核统计的"平均有多少任务在等待运行或等待 I/O"，用 `uptime` 看 1、5、15 分钟三个值。它高不一定代表 CPU 忙，也可能是磁盘卡住。

*inode*是文件系统描述一个文件的元数据结构。小文件极多时，`df -h` 显示还有空间，inode 却可能已耗尽，写入照样失败。

*结构化日志*是每行带固定字段（通常是 JSON）的日志，可以按字段过滤和统计，而不必靠文本匹配。

| 症状 | 先看什么 | 命令 | 这一步在排除什么 |
| --- | --- | --- | --- |
| 访问不通 | 进程在不在 | `systemctl status refund-worker`、`pgrep -a refund-worker` | 程序是否根本没运行 |
| 进程在但访问不通 | 端口有没有监听 | `ss -lntp`、`lsof -i :8080` | 绑定失败、绑错地址、端口被别的进程占用 |
| 连得上但很慢 | CPU 与负载 | `uptime`、`top` | 是否算力打满或线程卡死 |
| 偶发失败并伴随重启 | 内存与 OOM | `free -m`、`dmesg -T \| grep -i oom` | 进程是否被杀 |
| 写入报错 | 磁盘空间与 inode | `df -h`、`df -i`、`du -sh /var/log/*` | 空间或 inode 写满 |
| 新连接失败 | 文件描述符 | `ulimit -n`、`ls /proc/<PID>/fd \| wc -l` | 句柄泄漏 |

## 工作原理

诊断的本质是缩小假设空间，顺序比命令更重要：

1. **确定范围和起点**：是一个人、一部分人还是所有人？从几点开始？能稳定复现吗？先排除自己的网络与浏览器问题。
2. **看进程层**：`systemctl status` 给出最近几次重启与退出码；`pgrep -a` 给出 PID 与完整命令行。进程不在，问题就到此为止，转去 `journalctl` 查它为什么退出。
3. **看监听与连接**：`ss -lntp` 的本地地址列决定了服务能从哪里被访问，`0.0.0.0:8080` 才是所有网卡；`ss -tnp state established` 看有多少连接、堆积在哪个对端。
4. **看资源四件套**：CPU 与负载、内存是否触发 OOM、磁盘空间与 inode、文件描述符是否接近上限。这四类覆盖了单机故障的绝大多数。
5. **看日志**：先按时间窗口取（`journalctl --since`、`tail -n`），再按错误级别或请求 ID 过滤。关键是把日志时间与用户报障时间对齐。
6. **交叉验证并对齐时间线**：进程重启时间、端口监听时间、第一条错误的时间、告警时间必须能串成一条因果链；串不起来就说明还有没看到的证据。

回到业务场景：走到第 3 步三个事故就能分开——周一进程根本不存在，周三进程与端口都正常但磁盘满，周五只是地址列成了 `127.0.0.1`。

## 架构与选型

本课的裸机命令适合"单个实例、现场正在发生、需要马上给答案"的场景。它有明确边界：

| 手段 | 适用 | 不适用 | 代价 |
| --- | --- | --- | --- |
| 本机命令（`ps`、`ss`、`df`、`tail`） | 单实例现场排障，分钟级给出方向 | 多实例、容器内、重启后现场已丢 | 无历史，结论依赖操作者经验 |
| `journalctl` 与本地日志 | 看进程退出原因与错误上下文 | 日志分散在几十台机器上 | 需要登录机器，可能接触敏感数据 |
| 集中日志平台 | 多实例聚合、按请求 ID 串联 | 故障初期，来不及建索引 | 接入成本、采集延迟 |
| 指标与告警（Prometheus 一类） | 发现趋势、容量问题与回归 | 解释"为什么偏偏差这一个" | 需要预先埋点和合理阈值 |
| APM 与 Tracing | 跨服务定位慢在哪一跳 | 进程压根没起来的时候 | 侵入性、采样丢失 |

选型依据是三个问题：**现场还在不在**（还在就优先本机取样）、**实例有几个**（超过三个就该切到聚合视图）、**要不要给未来的自己留证据**（要就把关键输出粘进工单）。

## 最小示例

问题：上面那些命令都是"人读输出、人下判断"，能不能把其中三项变成一条可重复执行、有退出码的检查？下面是 `refund_diag.py`，只用标准库，Linux 与 macOS 都能直接运行。

```python
"""refund_diag.py —— 退款任务机的三项自检：端口、磁盘、日志错误率。仅用标准库。"""
import json
import os
import shutil
import socket

PORT = 18080                # 与 refund-worker 实际监听端口保持一致
LOG_PATH = "refund-worker.jsonl"
FREE_RATIO_WARN = 0.05      # 剩余空间低于 5% 视为风险：写满会连带拖垮整机
ERROR_RATIO_WARN = 0.10     # 最近窗口错误占比超过 10% 视为异常
WINDOW = 200                # 只看最近 200 行，避免历史故障污染当前判断


def probe_port(port, host="127.0.0.1", timeout=0.5):
    """一次 TCP 连接只回答“这个地址端口有没有人在 listen”，不代表业务健康。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)   # 不给超时会把脚本自己挂死，诊断工具不能变成故障源
        try:
            sock.connect((host, port))
        except OSError:
            return "DOWN"          # 拒绝连接或超时：进程没起，或只监听了别的地址
    return "UP"


def check_disk(path="."):
    """disk_usage 读文件系统元数据，与 df -h 同源，不需要 root。"""
    usage = shutil.disk_usage(path)
    ratio = usage.free / usage.total
    return ratio, "WARN" if ratio < FREE_RATIO_WARN else "OK"


def check_log(path=LOG_PATH, window=WINDOW):
    """按 JSON 字段判断而不是 grep 关键词：字段判断比文本匹配更抗日志格式变化。"""
    with open(path, encoding="utf-8") as handle:
        lines = handle.readlines()[-window:]  # 只留尾部窗口，和 tail -n 语义一致
    errors = 0
    for line in lines:
        try:
            if json.loads(line).get("level") == "ERROR":
                errors += 1
        except json.JSONDecodeError:
            errors += 1          # 解析不了的行本身就是故障信号，不能静默跳过
    ratio = errors / len(lines) if lines else 0
    return len(lines), errors, ratio, "WARN" if ratio > ERROR_RATIO_WARN else "OK"


def make_demo_log(path=LOG_PATH, total=200, error_every=12):
    """仅当样例日志缺失时生成演示数据；真实机器上要删掉这个函数。"""
    if os.path.exists(path):
        return
    with open(path, "w", encoding="utf-8") as handle:
        for i in range(1, total + 1):
            level = "ERROR" if i % error_every == 0 else "INFO"
            handle.write(json.dumps({"ts": "2026-10-19T10:00:00Z",
                                     "level": level, "task_id": f"RF-{7000 + i}"}) + "\n")


def main():
    make_demo_log()                       # 首次运行造样例数据，便于离线验证
    port_state = probe_port(PORT)
    free_ratio, disk_state = check_disk()
    total, errors, error_ratio, log_state = check_log()
    print(f"port  {PORT:<6} {port_state:<5} 检查目标：进程是否在监听")
    print(f"disk  free   {free_ratio:6.1%} {disk_state:<5} 阈值 {FREE_RATIO_WARN:.0%}")
    print(f"log   lines  {total:6d} {log_state:<5} 最近窗口 ERROR {errors} 条（{error_ratio:.1%}）")
    # 任何一项报警就返回非零退出码，这样它能直接被 cron 或 CI 当作断言使用
    return 0 if port_state == "UP" and "WARN" not in (disk_state, log_state) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

整体流程分三段：造数据、采三项证据、合成一个退出码。端口检查用一次 `connect` 而不是读配置文件，因为它回答的是"现在能不能连上"——那正是客服感受到的事实；日志检查按 `level` 字段解析而不是 `grep ERROR`，避免 `msg` 里带 "ERROR" 的正常日志被误计。

在一个没有任何服务监听 18080 的目录里运行：

```bash
python3 refund_diag.py; echo "exit=$?"
```

实际输出：

```text
port  18080  DOWN  检查目标：进程是否在监听
disk  free    30.6% OK    阈值 5%
log   lines     200 OK    最近窗口 ERROR 16 条（8.0%）
```

退出码为 `1`。用 `python3 -m http.server 18080` 起一个临时监听再跑一次，`port` 行变成 `UP`，退出码为 `0`——这一步同时证明了端口探测不是永远返回 `DOWN`。

## 动手实验

前置条件：一台 Linux 或 macOS 机器，`python3` 可用；一个可写的临时目录。全程不需要 root，也不需要外网。

1. 建立工作目录并进入：`mkdir -p ~/refund-diag && cd ~/refund-diag`。
2. 在本目录新建 `refund_diag.py`，内容与上一节完全一致。
3. 运行 `python3 refund_diag.py; echo "exit=$?"`，记录 `port` 行状态与退出码。
4. 起一个假服务占住端口：`python3 -m http.server 18080 &`，等待一秒后再运行一次，观察 `port` 行与退出码的变化。
5. 制造日志异常，把错误占比推高后再运行一次：
   ```bash
   for i in $(seq 1 40); do
     printf '{"ts":"2026-10-19T11:00:00Z","level":"ERROR","task_id":"RF-9%03d"}\n' "$i"
   done >> refund-worker.jsonl
   ```
6. 制造磁盘风险：把 `FREE_RATIO_WARN` 改成 `0.99`，再运行一次，观察 `disk` 行翻成 `WARN`。
7. 清理：`kill %1` 结束假服务，`rm -rf ~/refund-diag`。

预期结果：第 3 步 `port` 行为 `DOWN`、退出码 `1`；第 4 步 `port` 行为 `UP`、退出码 `0`；第 5 步 `log` 行翻 `WARN`、退出码 `1`；第 6 步 `disk` 行翻 `WARN`、阈值显示为 `99%`。

验证方法：每一步都用 `echo "exit=$?"` 确认退出码与你看到的状态一致。如果第 4 步仍显示 `DOWN`，用 `ss -lntp | grep 18080` 确认假服务真的在监听，而不是启动失败后静默退出。

清理方法见第 7 步。这个目录是一次性的，不要留在生产机或个人主目录里。

## 常见错误与排查

| 现象 | 可能原因 | 验证方法 | 修复方向 |
| --- | --- | --- | --- |
| `ss -lntp` 有监听但外部访问不通 | 只绑定了 `127.0.0.1` | 看 `ss` 输出的本地地址列 | 改绑 `0.0.0.0`，或调整探活与代理目标 |
| 进程在、端口不通 | 绑定失败后一直重试，或端口被别的进程占用 | `ss -lntp \| grep :8080`、`lsof -i :8080` | 在 `journalctl` 里找 address in use，腾出端口或改配置 |
| 进程反复重启 | OOM 被杀，或启动即崩 | `systemctl status` 看退出码、`dmesg -T \| grep -i oom` | 先查内存占用与泄漏，不要只把重启策略调激进 |
| CPU 不高但接口很慢 | 下游超时、连接池耗尽、磁盘 I/O 卡住 | `ss -s` 看连接状态、`top` 看 `wa` 值 | 按下游、池大小、磁盘三类继续收敛 |
| `df -h` 有空间但写入失败 | inode 耗尽 | `df -i` 看 inode 使用率 | 清理小文件与旧日志，配置日志轮转 |
| 日志里找不到报错 | 日志级别过高，或日志写到别处未被采集 | `journalctl -u refund-worker --since` 对齐时间窗 | 统一输出到标准输出并接入采集，补时间同步 |

## 安全与生产注意事项

**<u>排障时不要把整段日志直接贴进外部群或工单。</u>** 生产日志常带订单号、手机号、支付流水和访问令牌，复制一次就等于外发一次，后果是数据泄露与合规事故。缓解：只截取必要时间窗口与必要行，对敏感字段脱敏，并在工单注明"已脱敏"。

**<u>不要在取完证据前就 `kill -9` 或重启进程。</u>** 进程的内存、线程栈、`/proc/<PID>/` 下的现场与连接状态会在重启后全部消失，问题看似"恢复"却永远查不清原因。缓解方法：先执行 `ps`、`ss -tnp`、`tail` 把关键输出粘进工单，再处置。

另外，`du -sh /` 这类全盘扫描会带来大量磁盘 I/O，高峰期可能把"慢"变成"挂"，应限定到具体目录；非 root 执行 `ss -p` 看不到别人的进程名，那不是没有进程。

## 本课总结

- **诊断的产出是"被排除的假设清单"，不是一串命令。**
- 进程存在与端口被监听是两件事，`systemctl status` 和 `ss -lntp` 分别回答它们。
- CPU、内存、磁盘（含 inode）、文件描述符四类资源覆盖了单机故障的绝大多数。
- 日志要先按时间窗口取，再按字段过滤；只看错误级别会漏掉"没有报错但行为异常"。
- 把关键检查写成带退出码的脚本，才能从人肉排障变成可重复的检查。

## 思考题

`refund-worker` 目前单机运行，你需要为它设计一套"报障后 5 分钟内给出结论"的流程。请说明保留哪些本机命令、把哪些检查做成脚本、哪些依赖集中日志或指标，并解释容器化和多实例之后，哪一步会最先失效、为什么。

参考思路：先按"现场还在不在"分层——本机命令负责仍存活的进程与连接，脚本负责可重复的端口、磁盘、日志断言，集中日志与指标负责已重启或已过时间窗的部分。容器化后最先失效的通常是"登录机器看进程"，因为进程在容器命名空间里、容器可能已被重建，宿主机上既没有它的 PID，也没有它的 `/proc` 现场。

## 小测

1. 进程存在但端口没有被监听，最可能说明什么？
   A. 机器没有网络　B. 进程绑定端口失败或只绑定了别的地址　C. 防火墙关掉了所有端口　D. 日志级别配置错误
2. `df -h` 显示还有 12% 空间，但应用写入报 `No space left on device`，先查什么？
3. `uptime` 显示 15 分钟负载是 12，而 CPU 使用率只有 15%，这说明什么？
4. 为什么诊断脚本里的端口探测一定要设置超时？
5. 场景题：客服报"所有退款都超时"，值班同学第一反应是重跑数据库慢查询日志。你会在五分钟内按什么顺序取哪几项证据？

## 答案与解析

1. **B。** A 与"进程在跑"不冲突；C 表现为连不上而非没有监听；D 与端口无关。进程活着却没有监听，通常是绑定失败、端口被占或只绑了 loopback。
2. 先 `df -i` 看 inode。空间与 inode 是两个独立上限，小文件极多时先耗尽 inode；再用 `du -sh` 定位哪个目录在疯长。
3. 负载包含"等待 I/O 的任务"，所以高负载低 CPU 通常指向磁盘、网络或锁等待。下一步看 `top` 里的 `wa` 值和 `ss -s` 的连接状态，而不是继续查 CPU。
4. 没有超时的 `connect` 会在对端丢包时阻塞几十秒甚至更久，诊断工具本身就成了新的故障源；诊断脚本必须比它诊断的服务更快失败。
5. 建议顺序：①`systemctl status refund-worker` 判断进程与重启历史；②`ss -lntp` 与 `ss -tnp state established` 判断监听与连接堆积；③`free -m`、`dmesg -T | grep -i oom`、`df -h` 排除内存与磁盘；④`journalctl -u refund-worker --since` 对齐报障时间取错误上下文。重跑慢查询日志的前提已经是"数据库慢"这个未验证的假设，它既不解释"所有请求超时"的全量症状，也不会在五分钟内给出方向。

### 动手实验参考

第 4 步端口变 `UP` 说明探测有效；若仍是 `DOWN`，多半是假服务没起来（端口被占用时 `python3 -m http.server` 会直接退出）。第 5 步追加 40 行 ERROR 后，最近 200 行的错误占比升到 26% 左右，`log` 行翻 `WARN`、退出码 `1`。第 6 步把 `FREE_RATIO_WARN` 改成 `0.99` 后任何真实磁盘都会低于阈值，`disk` 行翻 `WARN`——这一步验证的是阈值逻辑，不是磁盘快满了。

## 延伸阅读与下一课

- [man7：proc(5)](https://man7.org/linux/man-pages/man5/proc.5.html) 解释 `/proc/<PID>/` 下每个文件的含义，是读懂进程现场的基础。
- [man7：ss(8)](https://man7.org/linux/man-pages/man8/ss.8.html) 是 `ss` 的完整参数手册，本课的监听与连接检查都出自这里。
- [systemd：journalctl](https://www.freedesktop.org/software/systemd/man/latest/journalctl.html) 给出按时间窗口与按 unit 过滤日志的官方用法。

- 返回[本单元目录](00-overview.md)。
- 回看上一课：[性能、安全与数据质量测试](06-performance-security-and-data-testing.md)。
- 下一课：[Docker 与 Docker Compose](08-docker-and-compose.md)。
