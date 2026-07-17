from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str


class VersionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_name: str
    api_version: str
    environment: str
