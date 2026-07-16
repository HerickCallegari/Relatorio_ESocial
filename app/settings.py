from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_secret_key: str = "dev-only-change-me"
    database_url: str = "sqlite:///./data/app.db"

    admin_username: str | None = None
    admin_password: str | None = None

    soc_base_url: str = "https://ws1.soc.com.br/WebSoc/exportadados"
    soc_empresa: str = ""
    soc_ws_usuario: str | None = None
    soc_ws_password: str | None = None

    soc_empresas_codigo: str = "192392"
    soc_empresas_chave: str = ""

    soc_inconsistencias_gerais_codigo: str = "205226"
    soc_inconsistencias_gerais_chave: str = ""

    soc_inconsistencias_2240_codigo: str = "218017"
    soc_inconsistencias_2240_chave: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
