from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongodb_uri: str
    mongodb_db: str = "rag_assistant"
    groq_api_key: str
    groq_model: str = "openai/gpt-oss-120b"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # Spreadsheet rows as SQL tables, for questions answered with SQL. Relative to backend/.
    sqlite_path: str = "data/tables.db"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
