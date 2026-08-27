"""Por onde a mensagem sai.

Uma interface so, com implementacoes trocaveis por variavel de ambiente. E a
peca que torna reversivel a decisao de usar Baileys em vez da API oficial:
**migrar depois de um banimento e trocar um segredo e reiniciar, nao reescrever
a funcionalidade.**

Nenhum teste da suite toca a rede — quem roda nos testes e o `fake`.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class EstadoDaConexao(StrEnum):
    CONECTADO = "CONECTADO"
    DESCONECTADO = "DESCONECTADO"
    AGUARDANDO_QR = "AGUARDANDO_QR"


@dataclass(frozen=True)
class Envio:
    """O resultado de uma tentativa. Nunca uma excecao: uma paciente com numero
    ruim nao pode impedir as outras sete de receberem."""

    ok: bool
    id_externo: str | None = None
    erro: str | None = None


class Provedor(Protocol):
    def estado(self) -> EstadoDaConexao: ...

    def enviar(self, *, numero: str, texto: str) -> Envio: ...
