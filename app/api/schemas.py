from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    dependencies: dict[str, str] | None = None


class VersionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    app_name: str
    api_version: str
