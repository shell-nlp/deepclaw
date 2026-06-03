# 渠道网关设计

## 目标

在当前仓库内新增一个渠道网关，使用户可以通过飞书、钉钉以及未来的其他消息渠道与现有智能体通信。网关需要支持多用户、会话级回复模式配置、实时流式回复和完整输出回复。用户级默认回复模式属于后续扩展。

设计边界是：渠道协议与智能体解耦。渠道代码可以知道如何调用智能体 API，但智能体不能知道飞书、钉钉或任何其他渠道。

## 现有智能体接口

现有智能体接口是：

```text
POST /api/agent/general_api
```

相关请求字段：

```text
query
resume
session_id
stream
user_id
internet_search
deep_thinking
mcp_config
```

接口会把 `session_id` 映射为 LangGraph 的 `thread_id`，因此 `session_id` 决定智能体的对话线程。`user_id` 通过 `AgentContext` 传入，用于标识用户。

响应是 SSE 流，事件类型包括：

```text
token
tool_calls
tool_output
__interrupt__
```

## 架构

在当前仓库中新增 `channels` 子系统：

```text
langchain_api/channels/
  adapters/
    feishu.py
    dingtalk.py
  models.py
  store.py
  service.py
  agent_client.py
  dispatcher.py

langchain_api/api/routers/channels.py
```

职责划分：

```text
adapters/
  负责渠道验签、webhook 事件解析、渠道消息发送和编辑。

models.py
  定义统一渠道消息模型和 SQLModel 数据表。

store.py
  封装 SQLModel 持久化。默认使用 SQLite。后续可以通过传入不同数据库 URL 支持 Postgres。

service.py
  编排用户/会话查找、回复模式选择、智能体调用和响应分发。

agent_client.py
  封装 /api/agent/general_api 调用，并输出统一的智能体事件。

dispatcher.py
  把智能体事件转换为渠道回复。支持 streaming 和 final 两种回复模式。

api/routers/channels.py
  注册飞书、钉钉 webhook 路由和会话配置接口。
```

## 数据库

使用 SQLModel。默认数据库为：

```text
sqlite:///<home_path>/channels.db
```

第一版不实现 Postgres，但 `store` 应接收 `db_url` 参数，后续可以使用类似下面的 URL：

```text
postgresql+psycopg://user:password@host:5432/dbname
```

### ChannelUser

`ChannelUser` 用于把外部渠道用户映射为内部 `user_id`。

```python
class ChannelUser(SQLModel, table=True):
    __tablename__ = "channel_users"

    id: int | None = Field(default=None, primary_key=True)
    channel: str = Field(index=True)
    channel_user_id: str = Field(index=True)
    user_id: str = Field(index=True)
    display_name: str | None = None
    created_at: datetime
    updated_at: datetime
```

`store` 应把 `channel + channel_user_id` 作为逻辑唯一键。

### ChannelSession

`ChannelSession` 用于把渠道会话映射为智能体 `session_id`。

```python
class ChannelSession(SQLModel, table=True):
    __tablename__ = "channel_sessions"

    id: int | None = Field(default=None, primary_key=True)
    channel: str = Field(index=True)
    channel_conversation_id: str = Field(index=True)
    channel_user_id: str = Field(index=True)
    user_id: str = Field(index=True)
    session_id: str = Field(index=True)
    reply_mode: str = Field(default="final")
    created_at: datetime
    updated_at: datetime
```

`channel_conversation_id` 是渠道侧会话标识，例如飞书 `chat_id` 或钉钉 `conversationId`。它用于定位消息应该回复到哪个渠道会话。

`session_id` 是内部智能体会话标识。它会发送给 `/api/agent/general_api`，并成为 LangGraph 的 `thread_id`。

默认映射策略：

```text
channel + channel_conversation_id + channel_user_id -> session_id
```

这样可以保证同一个用户在不同群聊、单聊或渠道里的上下文彼此隔离。

`store` 应把 `channel + channel_conversation_id + channel_user_id` 作为逻辑唯一键。

### ChannelMessageRecord

`ChannelMessageRecord` 用于 webhook 幂等和运行诊断。

```python
class ChannelMessageRecord(SQLModel, table=True):
    __tablename__ = "channel_message_records"

    id: int | None = Field(default=None, primary_key=True)
    channel: str = Field(index=True)
    message_id: str = Field(index=True)
    channel_conversation_id: str = Field(index=True)
    channel_user_id: str = Field(index=True)
    status: str = Field(default="received")
    error: str | None = None
    created_at: datetime
    updated_at: datetime
```

合法 `status` 值：

```text
received
processing
done
failed
```

`store` 应把 `channel + message_id` 作为逻辑唯一键。

## 统一消息模型

渠道适配器把飞书、钉钉等原始 webhook payload 转换为统一模型：

```python
class ChannelMessage(BaseModel):
    channel: str
    message_id: str
    channel_user_id: str
    channel_conversation_id: str
    text: str
    message_type: str = "text"
    raw: dict | None = None
```

`service` 只处理这个统一模型，不直接处理飞书或钉钉原始 payload。

## 消息流

```text
1. 飞书或钉钉发送 webhook 事件。
2. 渠道适配器验签，并解析为 ChannelMessage。
3. ChannelService 检查 ChannelMessageRecord，避免重复处理。
4. ChannelService 查找或创建 ChannelUser。
5. ChannelService 查找或创建 ChannelSession。
6. ChannelService 读取 ChannelSession.reply_mode。
7. AgentClient 使用 query、user_id、session_id、stream=true 调用 /api/agent/general_api。
8. Dispatcher 按选定回复模式发送渠道回复。
9. ChannelMessageRecord 标记为 done 或 failed。
```

webhook handler 应在校验和入库后尽快返回。第一版中，智能体执行和渠道回复发送放到后台任务中处理。

## 回复模式

系统支持两种会话级回复模式：

```text
final
streaming
```

### final

`dispatcher` 缓存 `token` 和必要的 `reasoning_token` 输出，等待智能体流结束后发送一条完整渠道消息。

新会话默认使用 `final`。

### streaming

`dispatcher` 创建或发送一条初始渠道消息，然后周期性编辑这条消息，把累积输出同步到渠道。

必须限制渠道编辑频率。初始建议：

```text
最多每 800 ms 编辑一次
或累计至少 20 个新字符后编辑一次
或遇到句号、换行等边界时编辑一次
```

具体编辑行为由渠道适配器实现，因为不同平台的消息 API 不同。

## 智能体事件处理

第一版处理策略：

```text
token
  追加到可见回复缓冲区。

tool_calls
  记录到日志，暂不展示给普通渠道用户。

tool_output
  记录到日志，暂不展示给普通渠道用户。

__interrupt__
  回复一条渠道可见消息，说明该操作需要人工确认，当前渠道暂不支持处理。
```

后续可以把 `__interrupt__` 转换成飞书或钉钉卡片，支持 approve、edit、reject 操作。

## 并发控制

第一版中，同一个 `session_id` 的消息应串行处理，避免两个智能体请求同时写入同一个 LangGraph 线程，导致上下文顺序混乱。

初始实现可以使用进程内锁：

```text
dict[session_id, asyncio.Lock]
```

这适合单进程开发和验证。多实例部署时，后续应替换为数据库锁、Redis 锁或基于队列的分区处理。

## 幂等

使用 `channel + message_id` 防止渠道 webhook 重试导致重复调用智能体。

重复 webhook 到达时：

```text
status = received 或 processing
  返回成功，不启动新的智能体任务。

status = done
  返回成功，默认不重复发送消息。

status = failed
  默认返回成功。显式重试或人工重试后续再增加。
```

## 错误处理

如果智能体调用失败：

```text
final 模式
  发送一条简短失败提示给渠道。

streaming 模式
  把占位消息或最近一次流式消息编辑成失败提示。
```

如果渠道发送失败，应把错误写入 `ChannelMessageRecord.error`，并把记录标记为 `failed`。

运行日志应包含：

```text
channel
message_id
channel_conversation_id
channel_user_id
user_id
session_id
reply_mode
error
```

## API 路由

新增：

```text
POST /api/channels/feishu/events
POST /api/channels/dingtalk/events
```

这些路由用于接收渠道 webhook 事件。

新增最小会话配置接口：

```text
GET  /api/channels/sessions
PATCH /api/channels/sessions/{session_id}
```

`PATCH` 支持修改：

```json
{
  "reply_mode": "streaming"
}
```

第一版配置优先级：

```text
ChannelSession.reply_mode
```

后续用户级默认值可以扩展为：

```text
ChannelSession.reply_mode
ChannelUser.default_reply_mode
系统默认 final
```

## 第一版不包含

第一版不实现：

```text
Postgres 迁移或部署
Redis 或分布式锁
Celery、RQ 或外部任务队列
跨渠道用户绑定
__interrupt__ 富卡片处理
向渠道用户展示 tool_calls 或 tool_output
图片、文件、语音或富文本消息转换
管理后台 UI
```

## 验证

实现阶段需要验证：

```text
SQLModel 可以使用默认 SQLite 数据库创建表。
ChannelStore 可以创建和读取 ChannelUser、ChannelSession。
重复 channel message_id 不会触发重复智能体调用。
final 模式会缓存 token，并只发送一条回复。
streaming 模式会节流编辑，而不是每个 token 都编辑一次。
会话配置 PATCH 会校验 reply_mode。
修改过的 Python 文件可以通过 py_compile。
```
