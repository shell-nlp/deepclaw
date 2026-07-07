FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
SHELL ["/bin/bash", "-c"]
# 备份原始源并替换为国内镜像源（以清华源为例）
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources \
    && sed -i 's/security.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && apt-get install -y \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 设置 UV 镜像源为清华大学源以加速依赖安装
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

WORKDIR /deepclaw

# 先复制依赖锁文件，利用 Docker 分层缓存
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-group dev --all-extras -v

# 依赖安装后再复制源码（源码改动不破坏依赖层缓存）
COPY ./ /deepclaw

RUN echo '[[ -f .venv/bin/activate ]] && source .venv/bin/activate' >> ~/.bashrc

# 把 venv 的 bin 放进 PATH
ENV PATH="/deepclaw/.venv/bin:$PATH"

CMD ["/bin/bash"]
