from __future__ import annotations

import os
import platform
import subprocess
import tempfile
import textwrap

from langchain_core.tools import tool
from pydantic import Field

_TIMEOUT_SECONDS = 60 * 10
_MAX_OUTPUT_CHARS = 5000

_RUNNER_TEMPLATE = """\
import sys as _sys, io as _io

_stdout = _io.StringIO()
_sys.stdout = _stdout

{USER_CODE}

_output = _stdout.getvalue()
_sys.stdout = _sys.__stdout__

if _output.strip():
    print(_output.strip())

_result = locals().get('result')
if _result is not None:
    print(f"result: {_result}")
"""


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """终止进程及其子进程树（跨平台）。"""
    if platform.system() == "Windows":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
        )
    else:
        proc.kill()


def _exec_via_uv(code: str) -> str:
    """通过 uv run 在子进程中执行 Python 代码，可使用项目全部依赖。"""
    wrapped_code = _RUNNER_TEMPLATE.replace("{USER_CODE}", textwrap.dedent(code).strip())

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(wrapped_code)
        temp_path = f.name

    proc = subprocess.Popen(
        ["uv", "run", "python", temp_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        stdout, stderr = proc.communicate(timeout=_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        proc.wait()
        return f"执行超时（>{_TIMEOUT_SECONDS} 秒），请简化代码或减少数据量"
    except FileNotFoundError:
        return "执行错误：未找到 uv 命令，请确认已安装 uv"
    except Exception as e:
        return f"执行异常：{type(e).__name__}: {e}"
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass

    if proc.returncode != 0:
        stderr = stderr.strip()
        if stderr:
            return f"执行错误：\n{stderr}"
        return f"执行错误（退出码 {proc.returncode}）"

    output = stdout.strip() if stdout else ""
    if not output:
        return "（代码已执行，无输出内容）"

    if len(output) > _MAX_OUTPUT_CHARS:
        output = output[:_MAX_OUTPUT_CHARS] + f"\n...（输出已截断，超过 {_MAX_OUTPUT_CHARS} 字符）"
    return output


@tool
def python_executor(
    code: str = Field(description="要执行的 Python 代码。用 result 变量保存返回值（如 result = df.mean()）"),
) -> str:
    """执行 Python 代码进行数据处理。通过 uv run 子进程运行，可使用项目全部依赖。

    可以导入和使用项目中 pyproject.toml 声明的任意库。

    限制：
    - 禁止文件/网络/进程操作
    - 超时 15 秒
    - 输出上限 5000 字符
    - 用 result 变量保存返回值，print 输出也会被捕获
    """
    return _exec_via_uv(code)


if __name__ == "__main__":
    print(python_executor.invoke({"code": "result = 1"}))
