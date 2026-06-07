from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
