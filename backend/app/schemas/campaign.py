from pydantic import BaseModel, Field, field_validator


class CampaignCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    country_code: str = Field(min_length=2, max_length=2, description="ISO 3166-1 alpha-2, например DE")
    offer_id: int = Field(gt=0)
    domain_id: int = Field(gt=0)
    group_id: int = Field(gt=0)
    traffic_source_id: int = Field(gt=0)

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 2 or not value.isalpha():
            raise ValueError("Ожидается двухбуквенный код страны, например DE или US")
        return value


class OfferAdd(BaseModel):
    offer_id: int = Field(gt=0)


class CampaignCreated(BaseModel):
    campaign_id: int
    alias: str | None = None
    name: str
    streams: list[dict]
    message: str
