# Channels 目录拆分设计

**日期：** 2026-06-09

**目标：** 将 `deepclaw/web_backend/channels/` 从“多渠道代码平铺混放”调整为“按渠道域拆分、共享能力收口”的结构，重点把 `weixin_clawbot` 从与 `feishu`、`dingtalk` 的混合实现中解耦出来，同时保留统一会话管理能力。

## 1. 背景与问题

当前 `channels` 目录同时承载了三类不同层次的职责：

- 顶层共享能力：会话模型、运行时状态存储、消息处理服务、鉴权依赖
- 渠道接入能力：`feishu`、`dingtalk`、`weixin_clawbot` 的消息适配
- 微信专属复杂逻辑：ClawBot API 客户端、登录二维码、runtime 轮询、启动恢复

现状问题主要有三点：

1. `router.py` 同时管理三种渠道的入口与微信专属管理接口，职责过重。
2. `lifespan.py`、`config.py`、`adapters/` 在目录层级上没有体现“共享能力”和“渠道专属能力”的边界。
3. `weixin_clawbot` 具有远高于 `feishu`、`dingtalk` 的复杂度，但当前仍与它们并列混放，后续扩展和维护成本偏高。

## 2. 设计目标

- 按渠道域拆分目录，让每个渠道的入口、适配器、专属配置与运行时逻辑在自己的子目录中闭合。
- 顶层 `channels` 只保留真正跨渠道共享的能力。
- 对外 API 按渠道分组，路径语义清晰。
- 共享会话接口继续保留在 `/api/channels/sessions`，避免复制统一能力。
- 不引入插件化或动态注册等过度抽象，保持实现直接、可读、易调试。

## 3. 不做的事

- 不在本次改动中引入新的渠道插件系统。
- 不重写 `ChannelService`、`ChannelStore` 的领域模型。
- 不把共享会话接口按渠道复制多份。
- 不顺带重构与本任务无关的 `auth`、`agent`、`rag` 逻辑。

## 4. 目标目录结构

目标结构如下：

```text
deepclaw/web_backend/channels/
├── __init__.py
├── common.py
├── config.py
├── models.py
├── router.py
├── schemas.py
├── service.py
├── session_router.py
├── store.py
├── dingtalk/
│   ├── __init__.py
│   ├── adapter.py
│   └── router.py
├── feishu/
│   ├── __init__.py
│   ├── adapter.py
│   └── router.py
└── weixin_clawbot/
    ├── __init__.py
    ├── adapter.py
    ├── client.py
    ├── lifespan.py
    ├── router.py
    ├── runtime.py
    ├── schemas.py
    ├── settings.py
    └── state.py
```

### 顶层目录职责

- `router.py`
  只负责创建 `/api/channels` 根路由，并装配：
  - `session_router`
  - `feishu.router`
  - `dingtalk.router`
  - `weixin_clawbot.router`

- `common.py`
  放跨渠道共享、但不属于存储或服务本身的辅助逻辑，例如：
  - actor 是否管理员判断
  - manager_user_id 解析
  - token 脱敏
  - 会话访问权限校验

- `config.py`
  只保留跨渠道公共配置，例如 `CHANNEL_AGENT_API_URL`。
  微信专属配置从这里移走。

- `session_router.py`
  只保留共享会话管理接口：
  - `GET /api/channels/sessions`
  - `PATCH /api/channels/sessions/{session_id}`

- `models.py`、`schemas.py`、`service.py`、`store.py`
  继续作为跨渠道共享模型与基础设施保留在顶层。

## 5. 各渠道设计

### 5.1 Feishu

`feishu` 目录保持轻量：

- `adapter.py`
  负责将 Feishu 回调解析成 `ChannelMessage`，以及发送/编辑回复消息。

- `router.py`
  只暴露 Feishu 专属入口：
  - `POST /api/channels/feishu/events`

Feishu 不引入 runtime、状态恢复或专属 settings。

### 5.2 DingTalk

`dingtalk` 目录与 Feishu 对齐：

- `adapter.py`
  负责 DingTalk 事件解析与消息发送。

- `router.py`
  只暴露：
  - `POST /api/channels/dingtalk/events`

这样 Feishu 与 DingTalk 的目录结构一致，便于后续扩展类似轻量渠道。

### 5.3 Weixin ClawBot

`weixin_clawbot` 作为高复杂度渠道独立成域，职责拆分如下：

- `adapter.py`
  负责消息转换、消息遍历、发送回复。

- `client.py`
  负责 ClawBot API 调用与请求异常封装。

- `settings.py`
  负责所有微信专属配置项：
  - `WEIXIN_CLAWBOT_API_BASE_URL`
  - `WEIXIN_CLAWBOT_PRINT_QRCODE_ON_STARTUP`
  - `WEIXIN_CLAWBOT_AUTO_POLL_ON_STARTUP`
  - `WEIXIN_CLAWBOT_LOGIN_POLL_INTERVAL_SECONDS`
  - `WEIXIN_CLAWBOT_MESSAGE_POLL_INTERVAL_SECONDS`
  - `WEIXIN_CLAWBOT_DEFAULT_REPLY_MODE`
  - `WEIXIN_CLAWBOT_REQUEST_TIMEOUT_SECONDS`

- `state.py`
  负责与 runtime state 相关的纯函数：
  - `state_key` 生成与解析
  - manager/owner user_id 解析
  - 访问校验辅助
  - token 脱敏等微信专属辅助函数

- `runtime.py`
  负责二维码确认后的持续轮询、消息消费、token/base_url 持久化恢复。

- `lifespan.py`
  负责 runtime 任务表的启动、恢复、停止。

- `schemas.py`
  负责微信专属的请求/响应 schema，例如二维码请求、绑定用户列表等。

- `router.py`
  只暴露微信专属 API，不混入其他渠道路由。

## 6. 路由设计

### 共享接口

保留统一会话能力：

- `GET /api/channels/sessions`
- `PATCH /api/channels/sessions/{session_id}`

保留共享会话接口的原因：

- `ChannelSession` 是跨渠道统一领域对象。
- 回复模式、权限判断、列表查询当前也是共享逻辑。
- 若为每个渠道重复暴露 sessions，会造成语义重复和实现分叉。

### 渠道专属接口

#### Feishu

- `POST /api/channels/feishu/events`

#### DingTalk

- `POST /api/channels/dingtalk/events`

#### Weixin ClawBot

- `POST /api/channels/weixin-clawbot/qrcode`
- `GET /api/channels/weixin-clawbot/qrcode/status`
- `POST /api/channels/weixin-clawbot/users/{user_id}/qrcode`
- `GET /api/channels/weixin-clawbot/users/{user_id}/qrcode/status`
- `GET /api/channels/weixin-clawbot/users`
- `DELETE /api/channels/weixin-clawbot/users/{user_id}`
- `POST /api/channels/weixin-clawbot/poll`

说明：

- 旧路径不再要求兼容。
- 新路径统一采用“渠道前缀 + 渠道内部资源”的分组方式。

## 7. 数据与服务边界

### 共享层保持不变的部分

- `ChannelStore`
  继续负责：
  - 会话读写
  - runtime state 读写

- `ChannelService`
  继续负责：
  - 渠道消息转统一会话消息后的处理
  - 回复模式选择
  - 调用 Agent 能力并通过 adapter 回写渠道

### 需要调整的边界

- `ChannelService` 对微信默认回复模式的读取，不再依赖顶层 `config.py`，改为从 `weixin_clawbot.settings` 引入。
- 会话权限相关的共享辅助逻辑，从当前超大的 `router.py` 中抽出到顶层 `common.py`。
- 微信 runtime 状态相关逻辑从顶层 `router.py`、`lifespan.py` 中剥离到 `weixin_clawbot` 子目录。

## 8. 生命周期接入设计

应用总生命周期仍然通过 `deepclaw/web_backend/lifespan.py` 接入渠道生命周期，但渠道层只暴露一个稳定的顶层入口，例如：

- 顶层 `channels.router` 负责路由装配
- 顶层 `channels` 对外暴露 `channel_lifespan`
- `channel_lifespan` 内部再委托 `weixin_clawbot.lifespan`

这样应用装配层不需要知道具体有哪些渠道内部实现细节，只依赖 `channels` 的统一出口。

## 9. 迁移策略

本次改动按“先移动边界，再修正导入，再调整装配”的顺序进行：

1. 创建 `feishu`、`dingtalk`、`weixin_clawbot` 子目录。
2. 把现有 `adapters/feishu.py`、`adapters/dingtalk.py`、`adapters/weixin_clawbot.py` 分别迁移为各自域内文件。
3. 把 `weixin_startup.py`、与微信相关的 `lifespan` 和 `config` 逻辑迁入 `weixin_clawbot`。
4. 从当前 `router.py` 中抽出：
   - 共享会话接口到 `session_router.py`
   - Feishu 路由到 `feishu/router.py`
   - DingTalk 路由到 `dingtalk/router.py`
   - 微信路由到 `weixin_clawbot/router.py`
5. 精简顶层 `router.py` 为装配器。
6. 统一修正 import、`__init__.py` 导出和应用生命周期接入。
7. 更新 `AGENTS.md` 中的 `channels` 结构描述。

## 10. 风险与控制

### 风险 1：导入路径变更导致启动失败

控制方式：

- 迁移时优先保留原有类名与函数名，减少行为变更。
- 完成后执行 `py_compile`、`ruff check` 和必要的 `pytest`。

### 风险 2：微信 runtime 恢复逻辑回归

控制方式：

- 先保持现有 runtime state 数据结构不变。
- 仅调整模块位置与导入，不改变持久化键名。

### 风险 3：共享权限校验被拆散后行为变化

控制方式：

- 将当前 `router.py` 中已存在的权限判定逻辑整体抽到 `common.py`，避免重写。

## 11. 测试与验证要求

至少覆盖以下验证：

- Python 语法检查：
  - `uv run python -m py_compile <changed_file.py>`

- 代码规范检查：
  - `uv run ruff check .`

- 与 channels 相关的测试（若存在或补充）：
  - `uv run pytest tests -q`

- 结构调整完成后，必须执行：
  - `codegraph index --force`

## 12. 成功标准

满足以下条件视为本次拆分完成：

- `feishu`、`dingtalk`、`weixin_clawbot` 均有独立子目录。
- 顶层 `channels` 不再直接承载微信专属 runtime 与 client 细节。
- 顶层 `router.py` 只做装配，不再堆积所有渠道实现。
- 对外 API 已按渠道分组。
- 共享会话接口继续保留在 `/api/channels/sessions`。
- `AGENTS.md` 已同步到真实结构。

## 13. 实施原则

- 先修边界，再考虑命名清理，不在本次任务中追求额外抽象。
- 保持共享层稳定，避免“目录重构”演变成“业务重写”。
- 针对 `weixin_clawbot` 做充分隔离，但不强迫 `feishu`、`dingtalk` 引入并不需要的复杂层次。

