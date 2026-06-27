from pydantic import BaseModel, Field, field_validator


class ServiceIdentifierRequest(BaseModel):
    service_id: str = Field(min_length=1, max_length=120)

    @field_validator("service_id")
    @classmethod
    def normalize_service_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Service id is required.")

        return normalized
