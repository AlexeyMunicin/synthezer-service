from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "voxsync"
    debug: bool = True
    secret_key: str

    #paths
    base_dir: Path = Path(__file__).resolve().parent.parent.parent
    storage_path: Path = Path("./storage")

    #models
    whisper_model: str = ""
    tts_model: str = ""

    #redis
    redis_url: str = "redis://localhost:6379/0"

    class Config:
        env_file = ".env"
        extra = "ignore"
    
    @property
    def jobs_dir(self) -> Path:
        path = self.storage_path / "jobs"
        path.mkdir(parents=True, exist_ok=True)
        return path
    
    @property
    def tmp_dir(self) -> Path:
        path = self.storage_path / "tmp"
        path.mkdir(parents=True, exist_ok=True)
        return path

settings = Settings()
