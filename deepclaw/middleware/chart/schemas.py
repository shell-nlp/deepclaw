from pydantic import BaseModel, Field


class StyleSchema(BaseModel):
    """图表样式配置"""
    palette: list[str] | None = Field(default=None, description="颜色调色板")
    backgroundColor: str | None = Field(default="#fff", description="背景色")


class DimensionsSchema(BaseModel):
    """图表尺寸配置"""
    width: int = Field(default=600, description="图表宽度")
    height: int = Field(default=400, description="图表高度")


class TitleSchema(BaseModel):
    """标题配置"""
    title: str = Field(default="", description="图表标题")
    axisXTitle: str = Field(default="", description="X 轴标题")
    axisYTitle: str = Field(default="", description="Y 轴标题")
