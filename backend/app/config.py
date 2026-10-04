from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    data_dir: Path = Path(__file__).resolve().parents[2] / "data"
    chroma_dir: Path = Path(__file__).resolve().parents[2] / "data" / "index"
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def policies_dir(self) -> Path:
        return self.data_dir / "policies"

    @property
    def templates_dir(self) -> Path:
        return self.data_dir / "templates"

    @property
    def cases_dir(self) -> Path:
        return self.data_dir / "cases"

    @property
    def eval_dir(self) -> Path:
        return self.data_dir / "eval"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key.strip())


settings = Settings()
