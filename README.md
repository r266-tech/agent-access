# Agent Access

**给中文开发者和中文用户使用的通用 Agent 访问层。把网站、App、API、本地软件和重复联网流程，优先沉淀成 agent-native CLI；只有 CLI/API 覆盖不了时，才进入浏览器、CDP 或 GUI 兜底。**

Agent Access 面向 Claude Code、Codex、Cursor、OpenClaw、Hermes、OpenAI Agents、本地智能体框架，以及任何需要稳定访问外部世界的 AI 编程/研究 agent。

这个仓库同时提供 Codex 插件包，但项目本体不是“Codex 插件”。Codex 插件只是一个分发 adapter；真正的核心是可复用的 CLI registry、薄 skill、references 和贡献规范。

如果这个项目帮你的 agent 少点网页、少猜接口、少丢上下文，欢迎 star。star 越多，中文 agent 工具生态越容易被更多开发者和维护者看到。

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Node >=20](https://img.shields.io/badge/node-%3E%3D20-339933.svg)](package.json)

## 为什么需要它

现在很多 agent 做联网和软件操作时，还在反复消耗上下文：

- 每次都重新点动态网页；
- 每次都重新发现隐藏接口；
- 从不稳定页面文本里硬解析；
- 登录态、cookie、浏览器 session 到处散落；
- 一个 agent 找到的路径，另一个 agent 很难接着用。

Agent Access 的打法是把重复访问变成可复用能力：

1. 先发现目标网站/软件/API 是否已有合适能力。
2. 优先走 companion CLI 或结构化 API。
3. 浏览器、CDP、Computer Use 只做开荒和兜底。
4. 稳定发现沉淀为 CLI 契约、registry 条目或 focused reference。
5. 凭据、cookie、浏览器 profile、账号标识和私有路径只留在用户本机。

## 适合谁

| 用户 / agent runtime | 使用方式 |
| --- | --- |
| 中文开发者 | 用 registry 和 CLI 契约给网站、App、本地软件沉淀 agent-native 工具。 |
| Claude Code | 直接使用 CLI、registry、SKILL 和 references。 |
| OpenAI Codex | 安装内置 Codex 插件，或直接调用 `agent-access` CLI。 |
| Cursor | 把 Agent Access 作为 rules / agent instructions 里的访问层约定。 |
| OpenClaw | 复用 registry、CLI contract 和 references。 |
| Hermes / Babata 风格本地 agent | 用同一层薄路由，叠加本地私有 overlay。 |
| 自定义 agent | 调 `agent-access list/info/doctor`，按 CLI contract 适配。 |

给 agent runtime 读取的短入口见 [AGENTS.md](AGENTS.md)。

## 你会得到什么

- 随插件打包的 `agent-access` CLI：查询 registry、运行 bundled companion CLI、查看安装/升级计划、doctor 检查、routing contract、verify、auth 路由、manifest 门禁、overlay 遮蔽审计、公开审计、贡献草稿。
- 可移植的 `registry.json`：登记 WeChat、Polymarket、小宇宙、豆瓣、大众点评、小红书等 companion CLI。
- 由 registry 派生的 `cli-manifest.json`：给 agent 和发布流程一个稳定发现面，避免 route 静默消失。
- 薄 skill：提醒 agent 怎么选工具，但不把所有规则塞进常驻 prompt。
- references：CLI 生成、auth/session 边界、浏览器兜底、贡献审核等操作说明。
- Codex 插件包：位于 `plugins/agent-access`，方便 Codex 用户安装。

装插件后，用户立即拥有核心 `agent-access` CLI、registry，以及插件内置的轻量 companion CLI。
agent 可以通过 `agent-access run <name> -- ...` 直接运行 bundled CLI，也可以通过
`agent-access info/install/update/verify` 发现、安装和检查外部 companion CLI。
这样基础插件保持小而可信，用户又不会卡在“不知道下一步怎么用”。
`agent-access list/info` 会暴露每个 route 的 `install.state`：
`installable` 表示 registry 已声明可执行安装命令和 doctor；`contract-only`
表示只有公开能力契约，独立 CLI 安装器还没发布，agent 不应假设用户机器上已经能运行该命令。
如果用户配置了本地私有 registry 或 overlay，`agent-access audit-overlay` 会报告它是否遮蔽了插件自带 route，避免 agent 误以为正在使用最新打包契约。

## 快速开始

直接从 GitHub 使用：

```bash
npx github:r266-tech/agent-access --help
npx github:r266-tech/agent-access list
npx github:r266-tech/agent-access contract --target douban --task "mark movie as watched"
npx github:r266-tech/agent-access verify wechat-cli
npx github:r266-tech/agent-access run pmkt -- --help
npx github:r266-tech/agent-access info wechat-cli
npx github:r266-tech/agent-access doctor wechat-cli
npx github:r266-tech/agent-access check-manifest
npx github:r266-tech/agent-access audit-overlay
```

从本地 checkout 使用：

```bash
git clone https://github.com/r266-tech/agent-access.git
cd agent-access
npm link

agent-access list
agent-access info wechat-cli
agent-access contract --target douban --task "mark movie as watched"
agent-access verify wechat-cli
agent-access run pmkt -- --help
agent-access install wechat-cli      # 默认只输出 dry-run 计划
agent-access install pmkt --run      # 为 bundled CLI 创建本地 PATH shim
agent-access doctor wechat-cli --run # 执行目标 CLI 的 doctor 命令
agent-access check-manifest          # 防止 registry route 与 manifest 漂移
agent-access audit-overlay           # 检查本地私有 registry 是否遮蔽打包 route
```

`install` 和 `update` 默认都是 dry-run。只有确定要修改本机环境时才加 `--run`。

## Codex 插件安装

从 GitHub 安装：

```bash
codex plugin marketplace add r266-tech/agent-access --ref main
codex plugin add agent-access --marketplace agent-access
```

从本地 checkout 安装：

```bash
codex plugin marketplace add .
codex plugin add agent-access --marketplace agent-access
```

升级 Codex 插件：

```bash
codex plugin marketplace upgrade agent-access
codex plugin add agent-access --marketplace agent-access
```

Companion CLI 通过 registry 里的命令升级：

```bash
agent-access update wechat-cli
agent-access update wechat-cli --run
```

## 首批 Registry

| 目标 | 命令 | 状态 | 边界 |
| --- | --- | --- | --- |
| 微信 / WeChat / Weixin 本地数据 | `wechat-cli`, `wx-cli` | 公开 release | 只读本地微信数据；不发消息，不控制 UI。 |
| Polymarket | `pmkt` | 插件内置，公开 release | 只读市场、事件、价格、结果、订单簿、交易和 holder 数据；不碰钱包凭据。 |
| 小宇宙 FM / Xiaoyuzhou | `xyz` | 公开源码 | 只读订阅、节目、转录、搜索和历史。 |
| 豆瓣电影 / Douban movie | `douban` | 插件内置，公开 release | 浏览器 session 读取；标记/评分默认 dry-run，显式 apply 才写。 |
| 大众点评 / Dianping | `dp`, `dianping` | 插件内置，公开 release | 读取店铺和评价；支持浏览器/session 或 stdin cookie 导入；不导出 cookie。 |
| 小红书 / Rednote / Xiaohongshu | `xhs` | 公开 PyPI 包 | 用户 session 留本机；写操作必须显式命令和用户确认。 |

`plugins/agent-access/skills/agent-access/registry.json` 是权威 registry。`source_status` 用来告诉 agent：这个 route 是现在可安装，还是只有公开契约、源码待发布。
发布门禁会强制这个语义：`public-release` / `public-source` route 必须声明安装命令和 doctor；
`contract-public-source-pending` route 必须保持 `source-pending`，不能混入假的 install 命令。

`plugins/agent-access/skills/agent-access/cli-manifest.json` 是从 registry 生成的确定性发现索引。发布前跑：

```bash
agent-access check-manifest
agent-access build-manifest --write
```

`build-manifest` 默认不会写文件；只有加 `--write` 才更新 manifest。若已有 manifest 里的 route 被移除，命令会失败，除非明确加 `--allow-removals` 表示这次删除已经被审核。
默认 manifest 生成只读取打包 `registry.json`，不会继承 `AGENT_ACCESS_REGISTRY` 私有覆盖。需要临时检查私有 registry 时，必须显式传 `--registry FILE --output FILE`，不要写回公开包。

## Agent-Native CLI 契约

一个适合 agent 使用的 companion CLI 应该提供：

- 默认稳定 JSON stdout；
- 确定性退出码；
- 可用的 `--help`，最好还有 `doctor`；
- 可继续读取的 ID、URL、cursor、cache ref 等句柄；
- 可脚本化的分页、过滤、排序和 fields；
- 清晰的读写边界；
- 写操作显式 flag 或 dry-run 默认；
- 本地化 auth/session 存储；
- 失败时给出可操作的 `error.next_action`。

核心目标很简单：让网站、App 和本地软件变成 agent 能组合、能复用、能审计的工具。

## 架构

Agent Access 分四层：

1. 通用薄层：registry、references、贡献流程、审计检查和 CLI helper。
2. Adapter：当前提供 Codex 插件；其他 agent package 可以指向同一套文件和 CLI。
3. Companion CLIs：面向具体网站、App、API、本地数据库和工作流的工具。
4. 用户本地状态：凭据、cookie、浏览器 session、API key、缓存和私有 overlay。

公开包不会自动合并私有 overlay。若设置了 `AGENT_ACCESS_REGISTRY`，或存在 `~/.agent-access/registry.json`、`~/.agent-access/registry.local.json`、`~/.agent-access/overlays/registry.json`，可用 `agent-access audit-overlay` 检查本地条目是否遮蔽打包 route。`--strict` 会把遮蔽报告当成失败，用于发布或排障门禁。

公开 registry 可以描述登录方式、安装命令和升级命令，但不能包含用户凭据、cookie、token、账号标识、浏览器 dump、HAR、原始日志或私有本地路径。

## 隐私和安全

Agent Access 不做被动遥测，不自动上传用户经验。

贡献草稿默认只在本地。任何内容公开前，都必须由用户或维护者显式审核、脱敏、提交。

发布前请跑公开审计：

```bash
npm test
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs audit-public .
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs check-manifest
node plugins/agent-access/skills/agent-access/scripts/agent-access.mjs audit-overlay
```

## 检索关键词

中文：AI agent 访问层，智能体工具路由，agent-native CLI，Agent CLI 注册表，AI 浏览器自动化替代方案，Claude Code 工具，Codex 插件，Cursor agent 工具，OpenClaw 工具，Hermes agent 工具，本地优先 agent 工具，微信 CLI，小红书 CLI，豆瓣 CLI，大众点评 CLI，小宇宙 CLI。

English: AI agent access layer, agent-native CLI, AI browser automation alternative, agent tool router, CLI registry for agents, Claude Code tools, Codex plugin, Cursor agent tools, OpenClaw tools, Hermes agent tools, Computer Use fallback, CDP fallback, local-first agent tools, WeChat CLI, Polymarket CLI, Xiaoyuzhou CLI, Douban CLI, Dianping CLI, Xiaohongshu CLI, Rednote CLI.

## 贡献

欢迎这些贡献：

- 新的 companion CLI 契约；
- agent 友好的 registry 条目；
- 稳定站点/App pattern 的 focused reference；
- 隐私友好的 auth/session adapter；
- 测试和公开审计 probe；
- 帮助中文开发者和 agent 选择正确能力面的文档。

见 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [SECURITY.md](SECURITY.md)。

## License

MIT.
