from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field

class Settings(BaseSettings):
    """
    Application settings, loaded via pydantic-settings from .env file or environment variables.
    """
    # Neo4j Database
    neo4j_uri: str = Field(default="bolt://localhost:7687")
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: SecretStr

    # LLM Settings
    llm_model: str = Field(default="openai/gpt-4o-mini")
    llm_api_key: SecretStr = Field(default=SecretStr("mock_key"))

    # Pi-hole Settings
    pihole_url: str = Field(default="http://pihole.local")
    pihole_password: str = Field(default="mock")

    # SMTP Notifications
    smtp_host: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587)
    smtp_username: str = Field(default="")
    smtp_password: SecretStr = Field(default=SecretStr(""))
    recipient_address: str = Field(default="")
    notification_level: str = Field(default="warning")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
