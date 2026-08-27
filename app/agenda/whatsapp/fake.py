"""O provedor de mentira: registra o que enviaria, e nao envia nada.

E com ele que as tasks 10 a 16 foram construidas e testadas — reserva,
idempotencia, expiracao, consentimento, chave geral e tela ficaram prontas
**sem uma mensagem real e sem o chip novo existir**.
"""

from app.agenda.whatsapp import Envio, EstadoDaConexao


class ProvedorFake:
    """Guarda os envios em memoria. Nos testes e o unico provedor que roda."""

    def __init__(
        self,
        *,
        erro: str | None = None,
        falhar_na: int | None = None,
        conectado: bool = True,
    ) -> None:
        # `erro` falha sempre; `falhar_na` falha so na enesima (1 = a primeira),
        # que e como se prova que uma falha no meio da fila nao para as outras.
        self.erro = erro
        self.falhar_na = falhar_na
        self.conectado = conectado
        self.enviadas: list[tuple[str, str]] = []
        self.tentativas = 0

    def estado(self) -> EstadoDaConexao:
        return (
            EstadoDaConexao.CONECTADO if self.conectado else EstadoDaConexao.DESCONECTADO
        )

    def enviar(self, *, numero: str, texto: str) -> Envio:
        self.tentativas += 1
        if self.erro is not None:
            return Envio(ok=False, erro=self.erro)
        if self.falhar_na == self.tentativas:
            return Envio(ok=False, erro="falha simulada")
        self.enviadas.append((numero, texto))
        return Envio(ok=True, id_externo=f"fake-{self.tentativas}")
