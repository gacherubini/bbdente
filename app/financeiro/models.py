"""Tabelas do modulo financeiro.

Uma tabela so: `parcela`. Recebimento e parcela com `pago_em` preenchido — duas
tabelas guardariam a mesma verdade em dois lugares, e um dos dois envelheceria
errado.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base

ZERO = Decimal("0.00")


class Parcela(Base):
    """Uma cobranca do paciente, paga ou nao.

    Vem de duas origens: as 28.244 linhas do `ARQFAT` do Dentalis e o que a
    clinica registrar daqui para frente.
    """

    __tablename__ = "parcela"
    __table_args__ = (
        # Os dois eixos de toda consulta do modulo: "quanto entrou no periodo" e
        # "o que venceu e nao foi pago".
        Index("ix_parcela_clinica_pago_em", "clinica_id", "pago_em"),
        Index("ix_parcela_clinica_vencimento", "clinica_id", "vencimento"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    clinica_id: Mapped[int] = mapped_column(ForeignKey("clinica.id"), index=True)
    # FK declarada por nome: financeiro NAO importa o modelo Paciente. Para o nome
    # do paciente, chame pacientes.service.
    paciente_id: Mapped[int] = mapped_column(ForeignKey("paciente.id"), index=True)

    # '01/03' como veio do Dentalis; vazio quando ele nao dizia, e nos
    # recebimentos avulsos registrados aqui.
    numero: Mapped[str] = mapped_column(String(10), default="", server_default="")
    vencimento: Mapped[date] = mapped_column(Date)

    valor_cobrado: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # O devido corrigido pelo Dentalis. Guardado porque existe, nao porque a
    # aplicacao o use: quem manda no relatorio e o cobrado e o pago.
    valor_corrigido: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=ZERO, server_default="0"
    )

    pago_em: Mapped[date | None] = mapped_column(Date)
    valor_pago: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=ZERO, server_default="0"
    )

    juros: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, server_default="0")
    multa: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=ZERO, server_default="0")
    desconto: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=ZERO, server_default="0"
    )

    # Nome da forma de pagamento (Dinheiro, Cheque...). No historico do Dentalis
    # e quase sempre nulo: 28.234 das 28.244 linhas tinham CODTPAG '00'.
    forma_pagamento: Mapped[str | None] = mapped_column(String(40))
    observacao: Mapped[str | None] = mapped_column(Text)

    # O Dentalis registrava carne regravando o SALDO a cada pagamento: sete
    # linhas com o mesmo vencimento e valor caindo 1.200, 1.050, 900... sao uma
    # divida so, nao sete. As linhas anteriores ficam marcadas aqui — continuam
    # no banco, mas nao entram na soma do que ha para receber.
    substituida: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

    # CODICLIE|PARCELA|DTVENCTO do Dentalis, para reconciliar depois.
    codigo_legado: Mapped[str | None] = mapped_column(String(40), index=True)
    # Dado suspeito e marcado, nunca corrigido no chute nem descartado.
    revisar_motivo: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )

    criado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    criado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    excluido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def saldo(self) -> Decimal:
        """O que falta receber. Derivado, nunca guardado: saldo em coluna e a
        mesma verdade em dois lugares, e um dos dois envelhece errado.

        Pode ser negativo — o paciente pagou a mais e tem credito. Sao 112 linhas
        assim no historico do Dentalis.
        """
        # `or ZERO` porque o default da coluna so vale no flush: uma parcela
        # recem-criada, ainda na memoria, tem valor_pago None.
        return (self.valor_cobrado or ZERO) - (self.valor_pago or ZERO)

    @property
    def quitada(self) -> bool:
        return self.saldo <= ZERO
