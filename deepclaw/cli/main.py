import subprocess

import typer

app = typer.Typer(
    name="deepclaw",
    help="DeepClaw CLI 工具 - 安装依赖与环境",
)


def _run_cmd(cmd: list[str], desc: str) -> None:
    """运行命令并实时输出日志，失败时退出。"""
    typer.echo(f"▶ {desc} ...")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        typer.echo(f"✗ {desc} 失败 (exit={e.returncode})", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"✓ {desc} 完成")


@app.command()
def install() -> None:
    """安装所有运行依赖：Playwright Chromium + Docker sandbox 镜像。"""
    install_playwright()
    install_docker()


@app.command()
def install_playwright() -> None:
    """安装 Playwright Chromium 浏览器（含系统依赖）。"""
    _run_cmd(
        ["playwright", "install", "--with-deps", "chromium"],
        "安装 Playwright Chromium",
    )


@app.command()
def install_docker() -> None:
    """拉取 sandbox Docker 镜像。"""
    images = [
        "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.1.0",
        "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/execd:v1.0.18",
        "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/egress:v1.0.13",
    ]
    for image in images:
        _run_cmd(["docker", "pull", image], f"拉取镜像 {image}")


def main() -> None:
    """CLI 入口。"""
    app()


if __name__ == "__main__":
    main()
