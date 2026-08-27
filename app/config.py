from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalizar_url(url: str) -> str:
    """Deixa qualquer URL de Postgres no formato que o psycopg 3 entende.

    O `fly postgres attach` grava 'postgres://...'; o SQLAlchemy nao conhece esse
    esquema, e 'postgresql://' sozinho procura o psycopg2, que nao instalamos.
    """
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo):]
    return url


class Config(BaseSettings):
    """Configuracao lida de variaveis de ambiente ou do .env local."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://bddente:bddente@localhost:5432/bddente"
    database_url_teste: str = "postgresql+psycopg://bddente:bddente@localhost:5432/bddente_teste"
    secret_key: str = "troque-isto-em-producao"
    sessao_horas: int = 12
    clinica_id_padrao: int = 1
    extrato_sqlite: str = "dados_extraidos/dentalis.sqlite"
    # Segredo do endpoint que o relogio externo chama (`POST /tarefas/lembretes`).
    # Vazio significa "nao ha tarefa agendada aqui", e o endpoint responde 404 —
    # ambiente sem segredo nao pode ter uma porta que qualquer um abre mandando o
    # cabecalho vazio.
    tarefas_token: str = ""
    # Em producao o cookie de sessao so viaja por HTTPS. Fica False no dev local
    # porque o navegador recusa cookie secure em http://localhost.
    cookie_seguro: bool = False

    @field_validator("database_url", "database_url_teste")
    @classmethod
    def _normalizar(cls, valor: str) -> str:
        return normalizar_url(valor)


config = Config()
