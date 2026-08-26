"""Fronteira publica do modulo financeiro.

Este modulo NAO consulta `lancamento` nem `paciente` direto: pergunta a
`clinico.service` e a `pacientes.service`. Da tabela `parcela` ele e o dono.

Dois numeros que parecem o mesmo e nao sao:

- **Recebido** e dinheiro que entrou no periodo (`parcela.valor_pago`).
- **Produzido** e tratamento feito no periodo (`lancamento.valor`).

Um tratamento feito em marco pode ser pago em julho. As telas mostram os dois
lado a lado justamente para isso ficar visivel em vez de escondido numa media.
"""

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.auditoria import registrar
from app.catalogo.service import categorias_de, nomes_de_convenio
from app.clinico.service import producao, producao_por_paciente, producao_por_procedimento
from app.clinico.service import producao_por_dia as producao_por_dia_do_clinico
from app.financeiro.models import Parcela
from app.pacientes.service import convenios_de, nomes_de

ZERO = Decimal("0.00")

# Antes de julho de 1994 o dinheiro era Cruzeiro Real; somar aquilo com Real da
# um numero sem significado. Os graficos comecam depois da poeira baixar.
ANO_MINIMO = 1995

SEM_CONVENIO = "não informado"


@dataclass(frozen=True)
class Resumo:
    recebido: Decimal
    produzido: Decimal
    a_receber: Decimal
    tratamentos: int


@dataclass(frozen=True)
class LinhaCobranca:
    parcela_id: int
    paciente_id: int
    paciente: str
    vencimento: date
    cobrado: Decimal
    pago: Decimal
    saldo: Decimal
    dias_vencida: int


def _vivas(clinica_id: int):
    return (Parcela.clinica_id == clinica_id, Parcela.excluido_em.is_(None))


def _decimal(bruto) -> Decimal:
    return Decimal(bruto or 0).quantize(Decimal("0.01"))


def recebido(sessao: Session, *, clinica_id: int, de: date, ate: date) -> Decimal:
    """Dinheiro que entrou no periodo. Segue a data do PAGAMENTO, nunca a do
    vencimento — parcela de 2020 paga hoje e dinheiro de hoje.

    Nao pula as parcelas `substituida`, de proposito: cada degrau de um carne
    registra um pagamento que aconteceu de verdade. O que se conta duas vezes
    num carne e a divida, nunca o dinheiro.
    """
    return _decimal(
        sessao.scalars(
            select(func.coalesce(func.sum(Parcela.valor_pago), 0)).where(
                *_vivas(clinica_id), Parcela.pago_em >= de, Parcela.pago_em <= ate
            )
        ).one()
    )


def a_receber_total(
    sessao: Session, *, clinica_id: int, de: date, ate: date
) -> Decimal:
    """Saldo do que venceu DENTRO do periodo: cobrado menos pago.

    E um numero do mes, na mesma regua dos outros tres do cartao. Ate 26/08/2026
    ele somava tudo desde 1996 (so `vencimento <= ate`, sem piso) e dava R$ 2
    milhoes — o carne do Dentalis inteiro, ao lado de tres numeros mensais. Nada
    que a clinica faz hoje entra ali: `registrar_recebimento()` cria a parcela ja
    quitada. Era um saldo historico que nao muda e nao vai ser recebido, afogando
    o que aconteceu no mes.

    Duas regras do calculo continuam, e as duas vem do dado real:

    - E `cobrado - pago`, e nao a soma das parcelas sem data de pagamento: 7.849
      parcelas do historico foram pagas pela METADE — tem data e ainda assim
      devem. Somar so as sem data esconderia mais da metade da divida.
    - As parcelas `substituida` ficam de fora. O Dentalis registrava carne
      regravando o saldo a cada pagamento, e somar todas as linhas do mesmo
      carne contava a mesma divida sete vezes.

    A divida acumulada nao sumiu do sistema: quem quer ve-la abre a lista de
    cobranca logo abaixo, que tem o corte proprio dela (`MESES_DE_COBRANCA`).
    """
    return _decimal(
        sessao.scalars(
            select(
                func.coalesce(
                    func.sum(Parcela.valor_cobrado - Parcela.valor_pago), 0
                )
            ).where(
                *_vivas(clinica_id),
                Parcela.substituida.is_(False),
                Parcela.vencimento >= de,
                Parcela.vencimento <= ate,
            )
        ).one()
    )


def resumo(sessao: Session, *, clinica_id: int, de: date, ate: date) -> Resumo:
    feito = producao(sessao, clinica_id=clinica_id, de=de, ate=ate)
    return Resumo(
        recebido=recebido(sessao, clinica_id=clinica_id, de=de, ate=ate),
        produzido=feito["valor"],
        a_receber=a_receber_total(sessao, clinica_id=clinica_id, de=de, ate=ate),
        tratamentos=feito["tratamentos"],
    )


def recebido_por_mes(sessao: Session, *, clinica_id: int, ano: int) -> list[Decimal]:
    """Doze posicoes, janeiro a dezembro. Mes sem movimento vem zero, nao some —
    buraco no meio do grafico e pior que barra baixa."""
    meses = [ZERO] * 12
    linhas = sessao.execute(
        select(
            func.extract("month", Parcela.pago_em),
            func.coalesce(func.sum(Parcela.valor_pago), 0),
        )
        .where(
            *_vivas(clinica_id),
            Parcela.pago_em >= date(ano, 1, 1),
            Parcela.pago_em <= date(ano, 12, 31),
        )
        .group_by(func.extract("month", Parcela.pago_em))
    ).all()
    for mes, soma in linhas:
        meses[int(mes) - 1] = _decimal(soma)
    return meses


def producao_por_dia(
    sessao: Session, *, clinica_id: int, ano: int, mes: int
) -> list[int]:
    """Um numero por dia do mes — 28, 29, 30 ou 31 posicoes, conforme o mes."""
    ultimo = calendar.monthrange(ano, mes)[1]
    por_dia = producao_por_dia_do_clinico(
        sessao, clinica_id=clinica_id, de=date(ano, mes, 1), ate=date(ano, mes, ultimo)
    )
    return [por_dia.get(date(ano, mes, dia), 0) for dia in range(1, ultimo + 1)]


def _fatias(soma_por_nome: dict[str, Decimal]) -> list[tuple[str, Decimal]]:
    """Da maior para a menor. Fatia sem valor nenhum nao vira fatia."""
    return sorted(
        ((nome, valor) for nome, valor in soma_por_nome.items() if valor > ZERO),
        key=lambda par: (-par[1], par[0]),
    )


def producao_por_categoria(
    sessao: Session, *, clinica_id: int, de: date, ate: date
) -> list[tuple[str, Decimal]]:
    """Quanto cada categoria de tratamento rendeu no periodo."""
    por_procedimento = producao_por_procedimento(
        sessao, clinica_id=clinica_id, de=de, ate=ate
    )
    categorias = categorias_de(
        sessao, clinica_id=clinica_id, procedimento_ids=por_procedimento
    )
    soma: dict[str, Decimal] = {}
    for procedimento_id, valor in por_procedimento.items():
        nome = categorias.get(procedimento_id, "sem categoria")
        soma[nome] = soma.get(nome, ZERO) + valor
    return _fatias(soma)


def producao_por_convenio(
    sessao: Session, *, clinica_id: int, de: date, ate: date
) -> list[tuple[str, Decimal]]:
    """Quanto veio de cada convenio no periodo, pelo convenio do paciente."""
    por_paciente = producao_por_paciente(sessao, clinica_id=clinica_id, de=de, ate=ate)
    convenio_do_paciente = convenios_de(
        sessao, clinica_id=clinica_id, paciente_ids=por_paciente
    )
    nomes = nomes_de_convenio(
        sessao,
        clinica_id=clinica_id,
        convenio_ids={c for c in convenio_do_paciente.values() if c},
    )
    soma: dict[str, Decimal] = {}
    for paciente_id, valor in por_paciente.items():
        convenio_id = convenio_do_paciente.get(paciente_id)
        nome = nomes.get(convenio_id, SEM_CONVENIO) if convenio_id else SEM_CONVENIO
        soma[nome] = soma.get(nome, ZERO) + valor
    return _fatias(soma)


# Sao 10.233 parcelas vencidas e nao quitadas no banco real, acumuladas desde
# 1996. Uma pagina com dez mil linhas nao e uma lista de cobranca, e um arquivo
# morto que trava o navegador.
LIMITE_DE_COBRANCA = 300


def a_receber(
    sessao: Session,
    *,
    clinica_id: int,
    ate: date,
    desde: date,
    limite: int = LIMITE_DE_COBRANCA,
) -> list[LinhaCobranca]:
    """A lista de cobranca: o que venceu ate `ate`, desde `desde`, e tem saldo.

    O corte por `desde` existe porque a divida acumulada desde 1996 nao e
    cobranca, e historia — e uma lista que comeca em 1996 nunca chega no que da
    para cobrar hoje. O `limite` e a segunda trava: dez mil linhas numa pagina
    nao ajudam ninguem a cobrar nada.
    """
    parcelas = list(
        sessao.scalars(
            select(Parcela)
            .where(
                *_vivas(clinica_id),
                # A linha superada por outra do mesmo carne ja foi cobrada na
                # seguinte: listar as duas cobraria a mesma divida duas vezes.
                Parcela.substituida.is_(False),
                Parcela.vencimento <= ate,
                Parcela.vencimento >= desde,
                Parcela.valor_cobrado > Parcela.valor_pago,
            )
            .order_by(Parcela.vencimento, Parcela.id)
            .limit(limite)
        )
    )
    # Uma consulta para todos os nomes: sao milhares de linhas no banco real, e
    # uma consulta por linha e a tela travando sozinha.
    nomes = nomes_de(
        sessao, clinica_id=clinica_id, paciente_ids={p.paciente_id for p in parcelas}
    )
    return [
        LinhaCobranca(
            parcela_id=p.id,
            paciente_id=p.paciente_id,
            paciente=nomes.get(p.paciente_id, "—"),
            vencimento=p.vencimento,
            cobrado=p.valor_cobrado,
            pago=p.valor_pago,
            saldo=p.saldo,
            dias_vencida=(ate - p.vencimento).days,
        )
        for p in parcelas
    ]


def anos_com_movimento(sessao: Session, *, clinica_id: int) -> list[int]:
    """Os anos que tem dinheiro registrado, do mais recente para o mais antigo.

    Alimenta o seletor da tela, e por isso e peneirado nos dois extremos:

    - **antes de 1995 sai** porque o dinheiro era outra moeda, e somar Cruzeiro
      com Real da um numero que nao significa nada;
    - **depois de hoje sai** porque dinheiro recebido e fato, nao promessa. O
      historico tem uma parcela com pagamento no ano 2203 — erro de digitacao de
      1996 que ninguem corrigiu. A linha continua no banco, marcada; o que ela
      nao pode e virar uma opcao de menu.
    """
    ano = func.extract("year", Parcela.pago_em)
    anos = sessao.scalars(
        select(ano)
        .where(*_vivas(clinica_id), Parcela.pago_em.isnot(None))
        .distinct()
        .order_by(ano.desc())
    ).all()
    limite = date.today().year
    return [int(a) for a in anos if ANO_MINIMO <= int(a) <= limite]


class RecebimentoInvalido(ValueError):
    """O que foi informado nao pode virar um recebimento."""


def _conferir(valor: Decimal, quando: date) -> None:
    if valor <= ZERO:
        raise RecebimentoInvalido("o valor recebido precisa ser maior que zero")
    if quando > date.today():
        # Recebimento e fato, nao promessa. Dinheiro que ainda nao entrou nao
        # pode entrar no caixa de hoje.
        raise RecebimentoInvalido("a data do recebimento nao pode estar no futuro")


def registrar_recebimento(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    paciente_id: int,
    valor: Decimal,
    quando: date,
    forma: str | None = None,
    observacao: str | None = None,
) -> Parcela:
    """Dinheiro que entrou sem parcela previa: vira parcela ja quitada.

    Uma tabela so para as duas coisas — cobranca e recebimento sao a mesma linha
    em momentos diferentes da vida dela.
    """
    _conferir(valor, quando)
    parcela = Parcela(
        clinica_id=clinica_id,
        paciente_id=paciente_id,
        numero="",
        vencimento=quando,
        valor_cobrado=valor,
        valor_pago=valor,
        pago_em=quando,
        forma_pagamento=forma,
        observacao=observacao,
        criado_por=usuario_id,
        criado_em=datetime.now(UTC),
    )
    sessao.add(parcela)
    sessao.flush()
    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="CRIAR",
        entidade="parcela",
        entidade_id=parcela.id,
        depois={
            "paciente_id": paciente_id,
            "valor_pago": str(_decimal(valor)),
            "pago_em": quando.isoformat(),
            "forma_pagamento": forma,
        },
    )
    return parcela


def quitar(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    parcela_id: int,
    valor: Decimal,
    quando: date,
    forma: str | None = None,
    observacao: str | None = None,
) -> Parcela:
    """Recebe dinheiro numa parcela que ja existia.

    Pagar menos que o saldo e pagamento PARCIAL: o valor entra, o resto continua
    devido. E assim que 7.849 parcelas do historico foram registradas, e o
    Dentalis guardava so a data do ultimo pagamento — aqui e igual, para o
    numero antigo e o novo continuarem significando a mesma coisa.
    """
    _conferir(valor, quando)
    parcela = sessao.scalars(
        select(Parcela).where(
            Parcela.id == parcela_id, *_vivas(clinica_id)
        )
    ).first()
    if parcela is None:
        raise LookupError("parcela nao encontrada")

    # Sempre com dois centavos na auditoria: um lado gravado como '0' e o outro
    # como '0.00' faz o registro parecer uma mudanca que nao houve.
    antes = {
        "valor_pago": str(_decimal(parcela.valor_pago)),
        "pago_em": parcela.pago_em.isoformat() if parcela.pago_em else None,
    }
    parcela.valor_pago = _decimal((parcela.valor_pago or ZERO) + valor)
    parcela.pago_em = quando
    if forma:
        parcela.forma_pagamento = forma
    if observacao:
        parcela.observacao = observacao
    sessao.flush()

    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="ATUALIZAR",
        entidade="parcela",
        entidade_id=parcela.id,
        antes=antes,
        depois={
            "valor_pago": str(_decimal(parcela.valor_pago)),
            "pago_em": quando.isoformat(),
            "forma_pagamento": parcela.forma_pagamento,
        },
    )
    return parcela
