from ag_ui_langgraph import add_langgraph_fastapi_endpoint,LangGraphAgent
from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from deepclaw.agents.general.agent import Agent
from deepclaw.agents.general.context import AgentContext
from deepclaw.web_backend.common.endpoints import add_general_api_endpoint


class GetHistoryRequest(BaseModel):
    session_id: str


def create_agent_router(checkpointer=None, store=None) -> APIRouter:
    router = APIRouter(prefix="/api/agent")
    ag_ui_router = APIRouter(tags=["agent-ag-ui"])
    general_api_router = APIRouter()
    agent = Agent(deep_agent=True, checkpointer=checkpointer, store=store).get_agent()

    add_langgraph_fastapi_endpoint(
        app=ag_ui_router,
        agent=LangGraphAgent(
            name="agent",
            description="DeepAgent service.",
            graph=agent,
        ),
        path="/ag_ui",
    )

    add_general_api_endpoint(
        app=general_api_router,
        agent=agent,
        path="/general_api",
        context=AgentContext,
        name="agent_general_api",
        tags=["agent-chat"],
    )

    router.include_router(ag_ui_router)
    router.include_router(general_api_router)

    @router.post("/get_state", description="获取agent state", tags=["agent-state"])
    async def get_state(request: GetHistoryRequest):
        """获取agent state, 输出形如：
                {
          "messages": [
            {
              "content": "看一下 env",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "040c0450-e877-4764-8587-819a4316df70"
            },
            {
              "content": "你是想查看环境变量吗？还是某个名为 `env` 的文件？\n\n让我先看看当前目录下有没有相关文件：\n\n",
              "additional_kwargs": {},
              "response_metadata": {
                "finish_reason": "tool_calls",
                "model_name": "qwen3.5",
                "model_provider": "deepseek"
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019f0257-2b68-7ce2-b6d1-6605919b61ac",
              "tool_calls": [
                {
                  "name": "ls",
                  "args": {
                    "path": "."
                  },
                  "id": "call_4dd84d578a28486a87bb0b28",
                  "type": "tool_call"
                }
              ],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 10245,
                "output_tokens": 50,
                "total_tokens": 10295,
                "input_token_details": {},
                "output_token_details": {}
              }
            },
            {
              "content": "['E:\\\\$RECYCLE.BIN/', 'E:\\\\.pnpm-store/', 'E:\\\\02-TS&JS-HTML版/', 'E:\\\\BaiduNetdiskDownload/', 'E:\\\\CHIKA登录器【4.6.1】.exe', 'E:\\\\Config/', 'E:\\\\Desktop/', 'E:\\\\Documents/', 'E:\\\\Downloads/', 'E:\\\\FCNSDownloads/', 'E:\\\\FiddlerCore4.dll', 'E:\\\\MultiMediaOpt/', 'E:\\\\Program Files (x86)/', 'E:\\\\System Volume Information/', 'E:\\\\WeGameApps/', 'E:\\\\_tmp_13732_94dd93964e7f14a18d07b584f79b3b94', 'E:\\\\_tmp_19920_8b7c9fa80f00f62326c8d3dd7fd48f42', 'E:\\\\_tmp_26912_e5556fcaf94db95005226c028e0bb50a', 'E:\\\\data/', 'E:\\\\docker/', 'E:\\\\efd.dll', 'E:\\\\f8caf78ba5f662a05016a79d5d8a3846/', 'E:\\\\game/', 'E:\\\\git_dir/', 'E:\\\\home/', 'E:\\\\ini/', 'E:\\\\libeay32.dll', 'E:\\\\makecert.exe', 'E:\\\\milvus/', 'E:\\\\models/', 'E:\\\\other/', 'E:\\\\pixcake/', 'E:\\\\project/', 'E:\\\\pythonlogs/', 'E:\\\\skills/', 'E:\\\\sqlite3.dll', 'E:\\\\ssleay32.dll', 'E:\\\\tmp/', 'E:\\\\video/', 'E:\\\\致谢.txt', 'E:\\\\项目文档/']",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "tool",
              "name": "ls",
              "id": "c5fc1325-9cf5-4d31-8ff9-ade00800c5a6",
              "tool_call_id": "call_4dd84d578a28486a87bb0b28",
              "artifact": null,
              "status": "success"
            },
            {
              "content": "目前看不到名为 `env` 的文件。你能具体说明一下你想看哪个 `env` 吗？\n\n- `.env` 环境变量配置文件？\n- `env.js` / `env.ts` 文件？\n- 某个项目下的环境变量？\n- 还是当前系统的环境变量？",
              "additional_kwargs": {},
              "response_metadata": {
                "finish_reason": "stop",
                "model_name": "qwen3.5",
                "model_provider": "deepseek"
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019f0257-323f-7a71-b2be-5841c3aed90a",
              "tool_calls": [],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 10729,
                "output_tokens": 63,
                "total_tokens": 10792,
                "input_token_details": {},
                "output_token_details": {}
              }
            },
            {
              "content": "很好",
              "additional_kwargs": {},
              "response_metadata": {},
              "type": "human",
              "name": null,
              "id": "838ee85f-5836-482a-b26b-bbc30e6202a3"
            },
            {
              "content": "谢谢！有什么具体任务需要我帮忙完成的吗？",
              "additional_kwargs": {},
              "response_metadata": {
                "finish_reason": "stop",
                "model_name": "qwen3.5",
                "model_provider": "deepseek"
              },
              "type": "ai",
              "name": null,
              "id": "lc_run--019f0263-29e3-70b2-824a-2123af700617",
              "tool_calls": [],
              "invalid_tool_calls": [],
              "usage_metadata": {
                "input_tokens": 10798,
                "output_tokens": 12,
                "total_tokens": 10810,
                "input_token_details": {},
                "output_token_details": {}
              }
            }
          ],
          "memory_contents": {
            "E:\\git_dir\\langchain-api\\.deepclaw\\workspace\\AGENTS.md": "# AGENTS.md\r\n\r\n你的工作目录是: .deepclaw/workspace/\r\n## 系统环境\r\n- 你的系统已经存在 python 和 node.js 环境\r\n- python命令是无效的，只能执行 python3 命令\r\n- 你只能在 .deepclaw 目录下执行操作,禁止越权操作\r\n\r\n## 要求\r\n- 用户的偏好要用中文记录在 /memories/preferences.md 文件中,如果文件不存在,则创建,如果文件存在,则用中文记录,要进行补充,不能直接覆盖,切记 路径要使用绝对路径：/memories/preferences.md\r\n\r\n"
          }
        }
        """
        logger.info(f"入参: {request.model_dump_json(indent=2)}")
        config = {"configurable": {"thread_id": f"{request.session_id}"}}
        state_snapshot = await agent.aget_state(config)
        state = state_snapshot.values
        return state

    return router
