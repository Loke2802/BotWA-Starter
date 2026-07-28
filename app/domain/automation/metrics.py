from pydantic import BaseModel


class AutomationMetrics(BaseModel):
    total_executions: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    retries: int = 0
