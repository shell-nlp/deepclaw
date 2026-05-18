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

WORKDIR /langchain-api

COPY ./ /langchain-api
RUN uv sync --no-group dev -v && source .venv/bin/activate && \
    uv cache clean && \
    echo '[[ -f .venv/bin/activate ]] && source .venv/bin/activate' >> ~/.bashrc

# 把 venv 的 bin 放进 PATH，后面可以直接用 openai-router 
ENV PATH="/langchain-api/.venv/bin:$PATH"

CMD ["/bin/bash"]