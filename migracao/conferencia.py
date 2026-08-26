"""Conferencia bloqueante da migracao.

Todos os numeros abaixo vieram do extrato verificado e estao documentados na spec
(secao 6) e em dados_extraidos/DICIONARIO.md. Se algum nao bater, a migracao aborta
sem gravar: melhor nao migrar do que migrar torto um prontuario de 30 anos.
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clinico.models import (
    Condicao,
    Lancamento,
    LancamentoRegiao,
    Odontograma,
    RespostaAnamnese,
)
from app.financeiro.models import Parcela
from app.pacientes.models import Paciente
from app.shared.dentes import TODOS_FDI
from app.shared.tipos import Escopo

# 5.561 linhas no ARQCLIEN, mas dois codigos ('1659/PT' e '4783/PT') aparecem
# duas vezes cada. Viram um cadastro so, com os contatos das duas linhas e a
# marcacao possivel_duplicata — o lancamento aponta para o codigo, nao para a
# linha, entao dois cadastros com o mesmo codigo dividiriam o historico.
# Mais dois cadastros que a migracao cria: o provisorio que recebe os 33
# lancamentos sem CODICLIE, e '1104/OR', que so existia no ARQORCAM e tem
# anamnese respondida.
ESPERADO_PACIENTES = 5_561
ESPERADO_LANCAMENTOS = 44_812
ESPERADO_REGIOES = 29_350
ESPERADO_CONDICOES = 9_629
ESPERADO_RESPOSTAS = 2_046
ESPERADO_SOMA = Decimal("3461389.07")

# ARQFAT: o livro-caixa. VALORPAG e o dinheiro que entrou de fato, e a soma
# dele bate com a dos lancamentos realizados (R$ 2.374.762,13) com R$ 3.553,60
# de diferenca em 30 anos — duas fontes independentes contando a mesma coisa.
ESPERADO_PARCELAS = 28_244
ESPERADO_COBRADO = Decimal("5808797.26")
ESPERADO_PAGO = Decimal("2378315.73")
ESPERADO_PARCELAS_SEM_PAGAMENTO = 7_546
ESPERADO_PACIENTES_COM_PARCELA = 5_340
# Cinco linhas com ano fora de 1900-2035 (0200, 0202, 0203, 9200). Entram com a
# data como veio, marcadas — preservar e marcar, nunca chutar o seculo.
ESPERADO_PARCELAS_MARCADAS = 5


class ConferenciaFalhou(RuntimeError):
    def __init__(self, divergencias: list[str]) -> None:
        self.divergencias = divergencias
        super().__init__(
            "a conferencia da migracao reprovou:\n  - " + "\n  - ".join(divergencias)
        )


def conferir(sessao: Session, clinica_id: int) -> list[str]:
    """Devolve a lista de divergencias. Lista vazia significa aprovado."""
    divergencias: list[str] = []

    def comparar(rotulo: str, encontrado, esperado) -> None:
        if encontrado != esperado:
            divergencias.append(f"{rotulo}: esperado {esperado}, encontrado {encontrado}")

    comparar(
        "paciente",
        sessao.query(Paciente).filter_by(clinica_id=clinica_id).count(),
        ESPERADO_PACIENTES,
    )
    comparar(
        "lancamento",
        sessao.query(Lancamento).filter_by(clinica_id=clinica_id).count(),
        ESPERADO_LANCAMENTOS,
    )
    comparar(
        "lancamento_regiao",
        sessao.query(LancamentoRegiao)
        .join(Lancamento, LancamentoRegiao.lancamento_id == Lancamento.id)
        .filter(Lancamento.clinica_id == clinica_id)
        .count(),
        ESPERADO_REGIOES,
    )
    comparar("condicao", sessao.query(Condicao).count(), ESPERADO_CONDICOES)
    comparar(
        "resposta_anamnese", sessao.query(RespostaAnamnese).count(), ESPERADO_RESPOSTAS
    )

    soma = sessao.query(
        func.coalesce(func.sum(Lancamento.valor), 0)
    ).filter_by(clinica_id=clinica_id).scalar()
    comparar("soma dos valores", Decimal(soma).quantize(Decimal("0.01")), ESPERADO_SOMA)

    orfaos = (
        sessao.query(Lancamento)
        .outerjoin(Odontograma, Lancamento.odontograma_id == Odontograma.id)
        .filter(Odontograma.id.is_(None))
        .count()
    )
    comparar("lancamento orfao", orfaos, 0)

    dentes_invalidos = sessao.scalars(
        select(func.count())
        .select_from(Lancamento)
        .where(
            Lancamento.dente.isnot(None),
            Lancamento.dente.notin_(list(TODOS_FDI)),
        )
    ).one()
    comparar("dente fora da notacao FDI", dentes_invalidos, 0)

    boca_com_dente = (
        sessao.query(Lancamento)
        .filter(Lancamento.escopo == Escopo.BOCA, Lancamento.dente.isnot(None))
        .count()
    )
    comparar("lancamento de boca com dente preenchido", boca_com_dente, 0)

    regiao_fora_de_escopo = (
        sessao.query(LancamentoRegiao)
        .join(Lancamento, LancamentoRegiao.lancamento_id == Lancamento.id)
        .filter(Lancamento.escopo != Escopo.REGIOES)
        .count()
    )
    comparar("regiao em lancamento sem escopo REGIOES", regiao_fora_de_escopo, 0)

    comparar(
        "parcela",
        sessao.query(Parcela).filter_by(clinica_id=clinica_id).count(),
        ESPERADO_PARCELAS,
    )
    cobrado = sessao.query(
        func.coalesce(func.sum(Parcela.valor_cobrado), 0)
    ).filter_by(clinica_id=clinica_id).scalar()
    comparar(
        "soma cobrada", Decimal(cobrado).quantize(Decimal("0.01")), ESPERADO_COBRADO
    )
    pago = sessao.query(
        func.coalesce(func.sum(Parcela.valor_pago), 0)
    ).filter_by(clinica_id=clinica_id).scalar()
    comparar("soma paga", Decimal(pago).quantize(Decimal("0.01")), ESPERADO_PAGO)
    comparar(
        "parcela sem pagamento",
        sessao.query(Parcela)
        .filter(Parcela.clinica_id == clinica_id, Parcela.pago_em.is_(None))
        .count(),
        ESPERADO_PARCELAS_SEM_PAGAMENTO,
    )
    comparar(
        "paciente com parcela",
        sessao.query(func.count(func.distinct(Parcela.paciente_id)))
        .filter(Parcela.clinica_id == clinica_id)
        .scalar(),
        ESPERADO_PACIENTES_COM_PARCELA,
    )
    comparar(
        "parcela marcada para revisar",
        sessao.query(Parcela)
        .filter(
            Parcela.clinica_id == clinica_id,
            func.cardinality(Parcela.revisar_motivo) > 0,
        )
        .count(),
        ESPERADO_PARCELAS_MARCADAS,
    )

    return divergencias
