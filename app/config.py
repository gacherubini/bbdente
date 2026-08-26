from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Configuracao lida de variaveis de ambiente ou do .env local."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://bddente:bddente@localhost:5432/bddente"
    database_url_teste: str = "postgresql+psycopg://bddente:bddente@localhost:5432/bddente_teste"
    secret_key: str = "troque-isto-em-producao"
    sessao_horas: int = 12
    clinica_id_padrao: int = 1
    extrato_sqlite: str = "dados_extraidos/dentalis.sqlite"
    # Em producao o cookie de sessao so viaja por HTTPS. Fica False no dev local
    # porque o navegador recusa cookie secure em http://localhost.
    cookie_seguro: bool = False


config = Config()
