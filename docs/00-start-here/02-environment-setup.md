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
last_reviewed: 2026-10-16
---

# 环境准备

## 最小环境

- Python 3.11 或更高版本。
- 一个能显示 Markdown 的编辑器。
- 终端和 `curl`。
- Git。

部分实验会给出 Docker Compose 选项，但课程正文不要求先安装完整云环境。

## 检查命令

```bash
python3 --version
curl --version
git --version
```

每条命令都应输出版本信息。若系统只有 `python` 命令，可将后续 `python3` 替换为它。

## 凭据原则

不要把 API Key、密码或个人数据写入课程文件、Shell 历史或 Git。需要外部服务的实验必须优先使用 Mock 或离线替代方案。

下一步：[解决方案生命周期](03-solution-lifecycle.md)。
