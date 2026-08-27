"""O provedor de mentira: registra o que enviaria, e nao envia nada.

E com ele que as tasks 10 a 16 foram construidas e testadas — reserva,
idempotencia, expiracao, consentimento, chave geral e tela ficaram prontas
**sem uma mensagem real e sem o chip novo existir**.
"""

from app.agenda.whatsapp import Conexao, Envio, EstadoDaConexao

# Um PNG de 1x1 transparente. E o "QR" do provedor de mentira: a tela precisa de
# alguma imagem para provar que sabe mostrar uma, e esta nao parece um QR de
# verdade — ninguem vai tentar ler com o celular achando que funciona.
QR_DE_MENTIRA = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


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
        self.pareamentos = 0
        self.desconexoes = 0

    def estado(self) -> EstadoDaConexao:
        return (
            EstadoDaConexao.CONECTADO if self.conectado else EstadoDaConexao.DESCONECTADO
        )

    def conexao(self) -> Conexao:
        if not self.conectado:
            return Conexao(estado=EstadoDaConexao.DESCONECTADO)
        return Conexao(estado=EstadoDaConexao.CONECTADO, numero="5551999990000")

    def parear(self) -> Conexao:
        """Devolve o QR de mentira, e nao conecta nada — pareamento de verdade
        precisa de um celular do outro lado."""
        self.pareamentos += 1
        return Conexao(estado=EstadoDaConexao.AGUARDANDO_QR, imagem=QR_DE_MENTIRA)

    def desconectar(self) -> bool:
        self.desconexoes += 1
        self.conectado = False
        return True

    def enviar(self, *, numero: str, texto: str) -> Envio:
        self.tentativas += 1
        if self.erro is not None:
            return Envio(ok=False, erro=self.erro)
        if self.falhar_na == self.tentativas:
            return Envio(ok=False, erro="falha simulada")
        self.enviadas.append((numero, texto))
        return Envio(ok=True, id_externo=f"fake-{self.tentativas}")
