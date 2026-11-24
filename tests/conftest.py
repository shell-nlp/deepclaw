"""Pytest 全局配置。

在导入 deepclaw.settings 之前固定认证开关，避免本地 .env 的公网策略
影响依赖游客身份的既有用例。
"""

import os

os.environ.setdefault("ALLOW_GUEST_ACCESS", "true")
os.environ.setdefault("AUTH_ALLOW_REGISTRATION", "true")
