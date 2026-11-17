from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", case_sensitive=False)
    database_url: str = "postgresql+asyncpg://assessment:assessment_local@127.0.0.1:5432/assessment"
    data_dir: Path = ROOT / "data"
    rulings_dir: Path = ROOT / "rulings"
    model_mode: str = "mock"
    model_base_url: str = "https://api.deepseek.com"
    model_id: str = ""
    model_api_key: str = Field(default="", repr=False)
    model_input_cny_per_million: float = Field(default=0, ge=0)
    model_output_cny_per_million: float = Field(default=0, ge=0)
    model_max_output_tokens: int = Field(default=2048, ge=128, le=8192)
    model_timeout_seconds: float = Field(default=60, gt=0, le=300)
    model_concurrency: int = Field(default=2, ge=1, le=8)
    total_budget_cny: float = Field(default=200, gt=0, le=200)
    budget_warning_cny: float = 160
    embedding_mode: str = "local"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_revision: str = "7999e1d3359715c523056ef9478215996d62a620"
    embedding_threads: int = Field(default=4, ge=1, le=16)
    kafka_bootstrap_servers: str = "127.0.0.1:9092"
    kafka_topic: str = "assessment.imports"
    kafka_consumer_group: str = "assessment-worker"
    redis_url: str = "redis://127.0.0.1:6379/0"
    demo_password: str = Field(default="local-demo-change-me", repr=False)
    bridge_token: str = Field(default="", repr=False)
    qq_allowed_sessions: str = ""
    qq_bot_id: str = ""
    qq_live_enabled: bool = False
    cache_ttl_seconds: int = 300
    lease_seconds: int = 60
    heartbeat_seconds: int = 10
    max_job_attempts: int = 3
    retry_delays: tuple[int, int] = (10, 30)
    create_schema: bool = False
    seed_users: bool = True
    enable_test_faults: bool = False
    public_service_token: str = Field(default="", repr=False)

    @property
    def qq_allowlist(self) -> set[str]:
        return {item.strip() for item in self.qq_allowed_sessions.split(",") if item.strip()}
