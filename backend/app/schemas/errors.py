from typing import Literal
from pydantic import BaseModel
from typing import Optional

class ErrorResponse(BaseModel):
    success: Literal[False] = False
    message: str
    error_code: str | None = None
    error_details: list[dict] | None = None
    error_name: Optional[str] = None
