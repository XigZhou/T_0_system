---
name: china-quant-backtest
description: 工作区内默认启用的 A 股量化研究、回测、Tushare 数据、中文文档交付与腾讯云运维协作规则。
---

# China Quant Backtest

## 说明

这个 skill 用于 A 股量化研究与回测项目。它把常见的 Tushare 取数约定、中文文档交付要求、README 复现要求，以及腾讯云服务器操作约定沉淀到工作区内，减少每次对话重复说明。

如与仓库级 `AGENTS.md` 冲突，以 `AGENTS.md` 为准；如与用户当前回合的明确要求冲突，以用户要求为准。

## 使用流程

1. 先读仓库根目录下的 `AGENTS.md`、`README.md` 与相关 `docs/` 文档。
2. 涉及 Tushare、行情数据抓取、权限假设时，读取 [references/tushare-defaults.md](references/tushare-defaults.md)。
3. 涉及数据集、指标、README、前端入口或交付要求时，读取 [references/documentation-and-delivery.md](references/documentation-and-delivery.md)。
4. 涉及腾讯云、远程主机、SSH、部署或远程执行时，读取 [references/tencent-cloud-ops.md](references/tencent-cloud-ops.md)。
5. 对外说明完成前，先执行与改动直接相关的测试；如涉及 API、前端或回测行为，还需要做一次本地冒烟验证。

## 核心规则

- 默认从本机环境变量、SSH 配置或现有本地连接信息读取敏感信息，不要求用户重复粘贴。
- 默认使用中文编写数据说明、指标说明、README 更新与系统使用文档，除非用户明确要求英文。
- 项目数据说明与指标说明优先放在仓库根目录 `docs/` 下，与 `README.md` 同级。
- 面向交付的回测系统默认保留前端入口，除非用户明确要求只做 CLI。
- 本地验证未完成、仓库未确认可推送前，不声明 GitHub 交付已经完成。

## 典型适用场景

- A 股股票池、因子、指标、买卖条件与回测逻辑开发
- Tushare 数据拉取、清洗、落盘与权限假设说明
- 中文数据字典、指标文档、README、系统文档补充
- 腾讯云服务器上的部署、排障、远程执行与验证
