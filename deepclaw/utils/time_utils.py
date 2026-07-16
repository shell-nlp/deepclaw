"""时间相关工具。"""

from datetime import datetime
from zoneinfo import ZoneInfo

shanghai_tz = ZoneInfo("Asia/Shanghai")


def get_current_time() -> str:
    """返回上海时区的当前时间描述。

    Args:
        无额外参数。
    """

    weekday_map = {
        0: "星期一",
        1: "星期二",
        2: "星期三",
        3: "星期四",
        4: "星期五",
        5: "星期六",
        6: "星期日",
    }
    current_time = datetime.now(shanghai_tz)
    weekday_num = current_time.weekday()
    weekday_str = weekday_map[weekday_num]
    return f"\n当前时间：{current_time.year}年{current_time.month}月{current_time.day}日 {weekday_str}"
