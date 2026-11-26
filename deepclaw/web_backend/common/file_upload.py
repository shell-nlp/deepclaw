"""文件上传预检的公共协议。"""

from pydantic import BaseModel, Field


class FileFingerprint(BaseModel):
    """上传预检所需的原件指纹。"""

    extension: str = Field(max_length=64, pattern=r"^(?:\.[^/\\]+)?$")
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
