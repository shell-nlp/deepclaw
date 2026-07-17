from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class ChartDef:
    """图表定义"""
    name: str
    description: str
    schema: type
    render: Callable[[dict], str]
    annotations: dict | None = None
