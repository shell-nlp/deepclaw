# 默认只安装核心依赖，构建完整能力时传入：
# docker build --build-arg UV_EXTRAS="--all-extras" .
ARG UV_EXTRAS=""

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS python-builder

ARG UV_EXTRAS

# 备份原始源并替换为国内镜像源（以中科大源为例）
RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources \
    && sed -i 's/security.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources

# 仅构建阶段保留编译依赖，运行镜像不携带这些头文件和工具。
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 设置 UV 镜像源为阿里云源，并确保复制到运行镜像的虚拟环境不依赖构建缓存。
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    UV_LINK_MODE=copy

WORKDIR /deepclaw

# 先复制依赖锁文件，利用 Docker 分层缓存。
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-group dev --no-install-project $UV_EXTRAS

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

# 运行阶段仅保留数据库、字体和调试所需的系统包。
RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources \
    && sed -i 's/security.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    fontconfig \
    fonts-wqy-zenhei \
    curl \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /deepclaw

ENV PATH="/deepclaw/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/deepclaw/.deepclaw \
    XDG_CACHE_HOME=/deepclaw/.deepclaw/.cache \
    TZ=Asia/Shanghai

# 只复制运行时需要的虚拟环境、后端源码、MCP 工具和前端静态导出。
COPY --from=python-builder /deepclaw/.venv /deepclaw/.venv
COPY deepclaw ./deepclaw
COPY mcp2tool ./mcp2tool
COPY .sandbox.toml ./.sandbox.toml
# 前端由宿主或 CI 先执行 `cd frontend && pnpm build`，这里只复制导出产物。
COPY frontend/out ./frontend/out

# 运行用户只拥有运行时工作目录，源码保持只读。
RUN mkdir -p /deepclaw/.deepclaw/workspace \
    && chown -R 1000:1000 /deepclaw/.deepclaw

USER 1000:1000

EXPOSE 7869

CMD ["python", "-m", "deepclaw.main"]
