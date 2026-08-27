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

    # --- por onde a mensagem sai -------------------------------------------
    # "fake" registra o que enviaria e nao fala com ninguem; "evolution" fala com
    # o WhatsApp de verdade. O padrao e o de mentira, e isso e a barreira: ligar o
    # envio real tem de ser um ato deliberado, nunca o resultado de esquecer de
    # configurar. Trocar de provedor depois de um banimento e mudar esta linha e
    # reiniciar — nao reescrever a funcionalidade.
    whatsapp_provedor: str = "fake"
    # A Evolution roda como app separado no Fly, alcancada pela rede privada. Sem
    # endereco publico de proposito: ela nao tem login, so a chave do cabecalho.
    evolution_url: str = "http://bddente-whatsapp.internal:8080"
    evolution_api_key: str = ""
    evolution_instancia: str = "bddente"
    # Prazo de toda chamada de rede. Curto porque quem espera e o relogio, que e
    # uma thread so: uma Evolution travada sem prazo para o relogio inteiro, e
    # relogio parado nao avisa que parou.
    evolution_timeout_s: float = 10.0

    @field_validator("database_url", "database_url_teste")
    @classmethod
    def _normalizar(cls, valor: str) -> str:
        return normalizar_url(valor)


config = Config()
