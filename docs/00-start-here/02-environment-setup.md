---
title: 环境准备
slug: environment-setup
module: course-foundation
stage: deliver
type: card
difficulty: beginner
duration: 20m
prerequisites:
  - learning-guide
outcomes:
  - 检查 Python 和终端环境
  - 安全管理实验配置
last_reviewed: 2026-11-18
---

# 环境准备

这里的目标不是一次装齐所有后端和云服务，而是先确认你能阅读课程、运行最小示例并保存练习记录。后续实验需要其他工具时，再按对应课程的说明准备。

## 最小环境

| 工具 | 在课程中承担的角色 |
| --- | --- |
| Python 3.11 或更高版本 | 运行课程中的 Python 示例和实验 |
| 一个能显示 Markdown 的编辑器 | 阅读课程、查看代码并记录练习结果 |
| 终端和 `curl` | 终端用于执行命令；`curl` 用于后续向 Web 服务发送 HTTP（Web 服务常用的请求协议）请求并查看响应 |
| Git | 管理课程文件和练习改动的版本 |

部分实验会给出 Docker Compose 选项，用配置一起启动多个容器化服务；这只是可选的实验方式，课程正文不要求先安装完整云环境。

## 检查命令

在终端中逐条运行：

```bash
python3 --version
curl --version
git --version
```

预期结果：每条命令都应输出版本信息。若系统只有 `python` 命令，可将后续 `python3` 替换为它。如果某条命令无法执行，先记录系统提示，处理好对应工具后再继续需要它的实验。

## 凭据原则

API Key 是调用外部服务时使用的凭据，和密码一样需要保护。不要把 API Key、密码或个人数据写入课程文件、Shell 历史或 Git，也不要为了完成练习而把真实个人数据填进示例。

需要外部服务的实验必须优先使用 Mock 或离线替代方案。**Mock** 是用可控的模拟返回代替真实外部服务，让你不持有真实凭据也能练习请求、响应和失败处理。开始实验前，先查看该课给出的替代方式和清理步骤。

下一步：[解决方案生命周期](03-solution-lifecycle.md)。
