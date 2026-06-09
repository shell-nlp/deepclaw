# IM 绑定中心设计

**日期：** 2026-06-09

**目标：** 为本项目建立一套可扩展的多 IM 绑定中心，统一承载微信与飞书接入，并保留本项目相对 `nanobot` 的关键优势：多用户、多绑定、按系统用户隔离管理。

## 1. 背景

当前仓库已经具备：

- 统一的 `channels` 领域能力
- 微信 ClawBot 的用户级接入
- 飞书长连接的基础接入骨架
- 前端独立的“渠道管理”页面入口

但现状仍有三个明显限制：

1. 前端渠道管理仍然以“单个微信绑定”视角组织，尚未覆盖飞书，也不支持统一多绑定管理。
2. 后端 `binding` 数据虽已引入，但很多接口与存储逻辑仍然是“每个用户每个渠道最多一条绑定”的单绑定模型。
3. 管理员缺少一个统一的全局绑定总览，无法直接查看所有用户、所有渠道的绑定状态。

本次设计需要把渠道管理从“单渠道、单绑定、偏微信专用”推进到“多渠道、多绑定、统一管理”。

## 2. 设计目标

- 支持多个 IM 渠道，首批完整覆盖微信与飞书。
- 支持同一个系统用户在同一渠道下管理多条绑定。
- 每条绑定都具备独立的备注名、配置、状态与运行时实例。
- 普通用户只管理自己的绑定集合。
- 管理员可以查看并删除全局任意绑定。
- 前端继续保留单一“渠道管理”入口，不拆成多个顶级页面。
- 后端统一围绕 `binding_id` 建模，避免会话串线与删除误伤。

## 3. 非目标

- 本次不引入新的插件化渠道注册系统。
- 本次不重写 `ChannelService` 的整体职责，只补充 `binding_id` 维度。
- 本次不新增新的前端顶级导航入口。
- 本次不扩展钉钉、企业微信等新渠道的完整实现，但设计必须对后续接入友好。

## 4. 核心用户模型

### 4.1 系统用户与外部账号的关系

一个系统用户不是“每个渠道只能绑定一个外部账号”，而是：

- 一个系统用户可以绑定多个微信账号
- 一个系统用户可以绑定多个飞书应用/机器人
- 后续也可以绑定多个其他 IM 账号

例如：

- 系统用户 `zhangsan`
- 微信绑定：
  - `张三主号`
  - `李四代绑号`
- 飞书绑定：
  - `市场部机器人`
  - `客服值班号`

这些绑定都归属于 `zhangsan`，由 `zhangsan` 自己管理和删除；管理员也可以进行全局查看与删除。

### 4.2 备注名规则

每条绑定必须有一个 `display_name` 作为主标识，前端列表优先展示备注名，而不是直接依赖外部平台返回的真实账号名。

原因：

- 微信与飞书返回的可读名称不一定稳定
- 有些渠道在绑定早期拿不到可靠的人类可读名称
- 多绑定场景下，用户更需要一个自己定义的管理标识

## 5. 绑定模型设计

### 5.1 绑定是一等对象

后端以 `ChannelBinding` 作为渠道管理的一等对象，所有新增、编辑、删除、启停、状态查询都围绕 `binding_id` 执行。

每条绑定至少包含以下字段语义：

- `id`
  - 绑定唯一标识，即 `binding_id`
- `channel`
  - 渠道类型，例如 `weixin_clawbot`、`feishu`
- `owner_user_id`
  - 绑定归属的系统用户
- `manager_user_id`
  - 创建并管理该绑定的系统用户
- `display_name`
  - 绑定备注名
- `status`
  - 绑定整体状态，例如 `active`、`pending`、`error`
- `credentials`
  - 渠道凭据，例如飞书 `app_id/app_secret`、微信相关 token
- `config`
  - 渠道静态配置，例如飞书 `domain`、`group_policy`
- `runtime_state`
  - 运行时状态，例如二维码、长连接状态、bot 标识、错误信息

### 5.2 外部身份字段

本次直接在 `runtime_state` 中保存外部账号的稳定标识，例如：

- 飞书 bot `open_id`
- 飞书 app 信息
- 微信对应的 bot identity

如果绑定创建早期拿不到该值，则允许为空，并在 runtime 启动后回填。

## 6. 存储与查询边界

当前 `ChannelStore.upsert_binding()` 按 `channel + owner_user_id` 查找并更新第一条记录，这与“同一用户同一渠道多绑定”目标冲突。

因此需要调整为集合模型：

- `create_binding(...)`
  - 永远创建新绑定
- `get_binding(binding_id)`
  - 按主键查询单条绑定
- `update_binding(binding_id, ...)`
  - 只更新指定绑定
- `list_bindings(...)`
  - 支持按 `channel`、`owner_user_id`、`manager_user_id`、`status` 过滤
- `delete_binding(binding_id)`
  - 只删除单条绑定

对于微信运行时状态，不再把“一个 user_id 对应一个 runtime state”作为唯一来源，而要逐步迁移到“每条绑定各自拥有自己的 runtime 状态”。

## 7. 后端 API 设计

### 7.1 总体原则

- 集合查询走列表接口
- 单条操作走 `binding_id`
- 普通用户默认只看到自己的绑定
- 管理员可以查看所有绑定

### 7.2 通用列表接口

新增统一列表接口：

- `GET /api/channels/bindings`

支持以下查询参数：

- `scope`
  - `my` 或 `all`
- `channel`
  - 可选，过滤某个渠道
- `owner_user_id`
  - 管理员视角下可选
- `status`
  - 可选

语义：

- 普通用户只能使用自己的管理范围
- 管理员在 `scope=all` 时可以看到全量绑定

### 7.3 飞书接口

飞书不再使用 `/feishu/users/{user_id}/binding` 这种单绑定路径，改为集合化接口：

- `POST /api/channels/feishu/bindings`
  - 创建一条飞书绑定
- `PATCH /api/channels/feishu/bindings/{binding_id}`
  - 更新备注名、凭据、策略
- `GET /api/channels/feishu/bindings/{binding_id}`
  - 查询单条绑定详情
- `DELETE /api/channels/feishu/bindings/{binding_id}`
  - 删除单条绑定

创建参数至少包括：

- `owner_user_id`
- `display_name`
- `app_id`
- `app_secret`
- `domain`
- `group_policy`
- `streaming`
- 其他已支持的飞书配置项

### 7.4 微信接口

微信也需要从“按 user_id 单绑定”迁移到“按 binding_id 多绑定”：

- `POST /api/channels/weixin-clawbot/bindings`
  - 创建一条微信绑定并生成二维码
- `GET /api/channels/weixin-clawbot/bindings/{binding_id}`
  - 查询单条绑定详情
- `GET /api/channels/weixin-clawbot/bindings/{binding_id}/qrcode-status`
  - 查询该绑定的扫码状态
- `POST /api/channels/weixin-clawbot/bindings/{binding_id}/qrcode`
  - 重新生成二维码
- `DELETE /api/channels/weixin-clawbot/bindings/{binding_id}`
  - 删除单条绑定

创建参数至少包括：

- `owner_user_id`
- `display_name`

创建成功后返回：

- `binding_id`
- `qrcode`
- `qrcode_url`
- 当前状态

## 8. Runtime 与消息归属设计

### 8.1 runtime 归属

每条绑定都拥有独立 runtime：

- 一条飞书绑定对应一个飞书长连接 runtime
- 一条微信绑定对应一个微信轮询/扫码状态 runtime

runtime 的启动、停止、恢复都按 `binding_id` 管理。

### 8.2 消息归属

消息处理必须优先绑定到 `binding_id`，而不是继续依赖 `user_id + channel` 的粗粒度模型。

规则如下：

1. runtime 收到消息时，先定位自己所属的 `binding_id`
2. `adapter.parse_event()` 或 runtime 组装 `ChannelMessage` 时写入 `binding_id`
3. `ChannelService` 创建或查找会话时按 `binding_id` 维度隔离

这样可以保证：

- 同一系统用户挂了多个微信号时不会串会话
- 同一系统用户挂了多个飞书应用时不会串消息

### 8.3 删除规则

删除绑定时执行顺序：

1. 校验访问权限
2. 停止该 `binding_id` 对应 runtime
3. 删除绑定记录
4. 清理与该绑定直接关联的 runtime 状态

历史 `channel_sessions` 与 `message_records` 不要求物理删除，但必须避免后续继续被错误复用。

## 9. 权限设计

### 9.1 普通用户

普通用户只能：

- 查看自己管理的绑定
- 创建归属于自己的绑定
- 更新自己管理的绑定
- 删除自己管理的绑定

### 9.2 管理员

管理员可以：

- 查看全量绑定
- 按用户、渠道、状态筛选
- 删除任意绑定

本次不要求管理员在前端直接代替其他用户批量编辑所有渠道细节，但接口层要允许管理员查看与删除。

## 10. 前端信息架构

### 10.1 保持单一入口

继续沿用现有 `渠道管理` 入口，不新增顶级页面。

### 10.2 页面主结构

页面分为两个视角页签：

- `我的绑定`
- `管理员总览`，仅管理员可见

### 10.3 我的绑定

`我的绑定` 页面先按渠道展示卡片：

- 微信
- 飞书
- 后续可继续新增更多 IM

每个渠道卡片显示：

- 当前绑定数量
- 在线/异常状态统计
- `新增绑定` 按钮

点击渠道卡片后，展开该渠道下的绑定列表。

### 10.4 微信绑定交互

新增微信绑定的流程：

1. 输入 `备注名`
2. 创建绑定
3. 返回二维码
4. 前端生成一张独立绑定卡片

每张微信绑定卡片至少显示：

- 备注名
- 扫码状态
- 最近更新时间
- 二维码或二维码链接
- 操作：
  - `检查状态`
  - `重新生成二维码`
  - `删除`

### 10.5 飞书绑定交互

新增飞书绑定的流程：

1. 输入 `备注名`
2. 输入 `app_id`
3. 输入 `app_secret`
4. 选择 `domain`
5. 选择 `group_policy`
6. 创建绑定并尝试启动长连接 runtime

每张飞书绑定卡片至少显示：

- 备注名
- `app_id` 脱敏值
- 长连接状态
- 已识别的 bot/open_id 信息
- 操作：
  - `编辑`
  - `重连/重启`
  - `删除`

### 10.6 管理员总览

管理员总览采用列表或表格形式，不直接展示复杂编辑表单。

每行至少包含：

- 所属系统用户
- 渠道
- 备注名
- 当前状态
- 管理人
- 更新时间

支持以下筛选：

- 按系统用户筛选
- 按渠道筛选
- 按状态筛选

点击某条记录后再展开详情，查看运行状态并执行删除。

## 11. 兼容与迁移策略

### 11.1 接口迁移

旧接口在本次实现中保留兼容层，仅用于平滑迁移；新的前端必须全部切换到 `bindings` 语义接口。

长期目标是完全淘汰：

- `/feishu/users/{user_id}/binding`
- `/weixin-clawbot/users/{user_id}/qrcode`
- `/weixin-clawbot/users/{user_id}/qrcode/status`
- `/weixin-clawbot/users/{user_id}`

### 11.2 数据迁移

对于现有单绑定数据：

- 原有每个用户的微信状态，可迁移为一条默认绑定
- 原有每个用户的飞书绑定，可迁移为一条默认绑定
- 默认备注名可按现有规则生成，例如 `Weixin ClawBot {user_id}`、`Feishu {user_id}`

### 11.3 前端迁移

现有 `ChannelManagementView` 只管理微信，需要升级为统一绑定中心视图：

- 抽象通用“渠道区块”
- 抽象通用“绑定卡片”
- 保留微信二维码特有交互
- 新增飞书表单与状态卡片
- 新增管理员总览区

## 12. 异常处理

- 飞书凭据无效时，创建请求直接失败，不保留半启动 runtime。
- 微信二维码过期时，只刷新该绑定自己的二维码，不影响同用户其他绑定。
- runtime 启动失败时，绑定保留，但状态写为 `error`，前端允许重试。
- 所有敏感字段默认脱敏显示，尤其是：
  - `app_secret`
  - `bot_token`
  - 其他访问令牌

## 13. 测试要求

后端至少覆盖：

- 同一用户同一渠道创建多条绑定
- 删除其中一条不影响其他绑定
- 普通用户只能看到自己的绑定
- 管理员能看到全量绑定
- 微信二维码、状态查询、删除均按 `binding_id` 生效
- 飞书多 binding runtime 可独立启停
- 会话隔离按 `binding_id` 生效

前端至少覆盖：

- `我的绑定 / 管理员总览` 正确切换
- 微信多绑定卡片渲染正确
- 飞书多绑定卡片与表单渲染正确
- 新增、删除、重试后状态能正确刷新
- 管理员筛选总览时结果正确

验证命令至少包括：

- `uv run python -m py_compile <changed_file.py>`
- `uv run ruff check .`
- `uv run pytest tests -q`
- `codegraph index --force`
- 前端变更后：
  - `cd frontend`
  - `pnpm lint`
  - `pnpm build`

## 14. 成功标准

满足以下条件视为本次设计完成：

- 前端渠道页变成统一绑定中心，而不是仅管理单个微信绑定
- 微信与飞书都支持同一系统用户下的多绑定
- 所有单条操作都能稳定指向 `binding_id`
- 管理员可以在前端查看全局绑定总览
- 消息与会话按 `binding_id` 正确隔离
- 后续新增 IM 时，只需增加新的渠道区块与对应后端 binding/runtime 适配
