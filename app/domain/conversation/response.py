from pydantic import BaseModel, ConfigDict


class BusinessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str
    status: str
    tone: str = "neutral"
