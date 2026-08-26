"""Fronteira publica do modulo clinico.

Quando o modulo financeiro chegar, ele chama funcoes daqui — nunca consulta a
tabela lancamento direto.
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.auditoria import registrar
from app.catalogo.models import Procedimento
from app.clinico.models import (
    Condicao,
    Lancamento,
    LancamentoRegiao,
    Odontograma,
    PerguntaAnamnese,
    RespostaAnamnese,
)
from app.pacientes.service import obter as obter_paciente
from app.shared.dentes import (
    TODOS_FDI,
    canais_do_dente,
    canais_em_ordem_de_tela,
    e_anterior,
    e_fdi_valido,
    numero_de_raizes,
    paredes_do_dente,
)
from app.shared.tipos import Escopo, Regiao, StatusLancamento


def contar_pacientes_com_pendencia(sessao: Session, *, clinica_id: int) -> int:
    """Quantos pacientes tem ao menos um tratamento planejado. Uma agregacao so."""
    return sessao.scalars(
        select(func.count(func.distinct(Odontograma.paciente_id)))
        .select_from(Odontograma)
        .join(Lancamento, Lancamento.odontograma_id == Odontograma.id)
        .where(
            Lancamento.clinica_id == clinica_id,
            Lancamento.status == StatusLancamento.PLANEJADO,
            Lancamento.excluido_em.is_(None),
        )
    ).one()


def resumo_por_paciente(
    sessao: Session, *, clinica_id: int, paciente_ids: Iterable[int]
) -> dict[int, tuple[int, Decimal]]:
    """Para cada paciente, quantos tratamentos estao pendentes e quanto somam.

    Uma consulta agregada para a lista inteira — nunca uma por linha da tabela.
    """
    ids = list(paciente_ids)
    if not ids:
        return {}
    linhas = sessao.execute(
        select(
            Odontograma.paciente_id,
            func.count(Lancamento.id),
            func.coalesce(func.sum(Lancamento.valor), 0),
        )
        .join(Lancamento, Lancamento.odontograma_id == Odontograma.id)
        .where(
            Odontograma.paciente_id.in_(ids),
            Lancamento.clinica_id == clinica_id,
            Lancamento.status == StatusLancamento.PLANEJADO,
            Lancamento.excluido_em.is_(None),
        )
        .group_by(Odontograma.paciente_id)
    ).all()
    resumo: defaultdict[int, tuple[int, Decimal]] = defaultdict(
        lambda: (0, Decimal("0.00"))
    )
    for paciente_id, pendentes, soma in linhas:
        resumo[paciente_id] = (pendentes, Decimal(soma).quantize(Decimal("0.01")))
    return dict(resumo)


# Ordem de forca: o que esta por fazer nunca some atras do que ja foi feito.
FORCA = {"EXISTENTE": 0, "REALIZADO": 1, "PLANEJADO": 2}


class EscopoInvalido(ValueError):
    """Combinacao de escopo, dente e regioes que o dominio recusa."""


def _validar(escopo: Escopo, dente: int | None, regioes) -> None:
    if escopo is Escopo.BOCA:
        if dente is not None:
            raise EscopoInvalido("lancamento de boca toda nao pode ter dente")
        if regioes:
            raise EscopoInvalido("lancamento de boca toda nao pode ter regioes")
        return
    if dente is None:
        raise EscopoInvalido("lancamento em dente exige o numero do dente")
    if not e_fdi_valido(dente):
        raise EscopoInvalido(f"dente {dente} nao existe na notacao FDI permanente")
    if escopo is Escopo.REGIOES and not regioes:
        raise EscopoInvalido("escopo REGIOES exige ao menos uma regiao")
    if escopo is Escopo.DENTE and regioes:
        raise EscopoInvalido("escopo DENTE nao aceita regioes; use REGIOES")


def _odontograma_de(sessao: Session, paciente_id: int, numero: int) -> Odontograma:
    odontograma = sessao.scalars(
        select(Odontograma).where(
            Odontograma.paciente_id == paciente_id, Odontograma.numero == numero
        )
    ).first()
    if odontograma is None:
        odontograma = Odontograma(paciente_id=paciente_id, numero=numero)
        sessao.add(odontograma)
        sessao.flush()
    return odontograma


def lancar(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    paciente_id: int,
    procedimento_id: int,
    escopo: Escopo,
    dente: int | None = None,
    regioes: "list[Regiao] | tuple[Regiao, ...]" = (),
    status: StatusLancamento,
    data: date | None = None,
    valor: Decimal | None = None,
    observacao: str | None = None,
    numero_odontograma: int = 1,
) -> Lancamento:
    regioes = list(regioes)
    _validar(escopo, dente, regioes)

    odontograma = _odontograma_de(sessao, paciente_id, numero_odontograma)
    realizado = status is StatusLancamento.REALIZADO
    lancamento = Lancamento(
        clinica_id=clinica_id,
        odontograma_id=odontograma.id,
        dente=dente,
        escopo=escopo,
        procedimento_id=procedimento_id,
        status=status,
        data_planejada=data if not realizado else None,
        data_realizada=data if realizado else None,
        valor=valor if valor is not None else Decimal("0.00"),
        observacao=observacao,
        criado_por=usuario_id,
    )
    sessao.add(lancamento)
    sessao.flush()
    for regiao in regioes:
        sessao.add(LancamentoRegiao(lancamento_id=lancamento.id, regiao=regiao))
    sessao.flush()

    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="CRIAR",
        entidade="lancamento",
        entidade_id=lancamento.id,
        depois={
            "dente": dente,
            "escopo": escopo.value,
            "regioes": [r.value for r in regioes],
            "status": status.value,
            "valor": str(lancamento.valor),
            "procedimento_id": procedimento_id,
        },
    )
    return lancamento


def excluir_lancamento(
    sessao: Session, *, clinica_id: int, usuario_id: int, lancamento_id: int
) -> bool:
    """Exclusao LOGICA. Nunca ha DELETE: prontuario tem guarda minima de 10 anos."""
    lancamento = sessao.scalars(
        select(Lancamento).where(
            Lancamento.id == lancamento_id,
            Lancamento.clinica_id == clinica_id,
            Lancamento.excluido_em.is_(None),
        )
    ).first()
    if lancamento is None:
        return False
    lancamento.excluido_em = datetime.now(UTC)
    sessao.flush()
    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="EXCLUIR",
        entidade="lancamento",
        entidade_id=lancamento.id,
        antes={"dente": lancamento.dente, "escopo": lancamento.escopo.value},
    )
    return True


def estado_do_odontograma(
    sessao: Session, *, clinica_id: int, paciente_id: int, numero: int = 1
) -> dict:
    # Fronteira de modulo: clinico nao consulta a tabela paciente, pergunta ao
    # service de pacientes.
    paciente = obter_paciente(sessao, clinica_id=clinica_id, paciente_id=paciente_id)
    if paciente is None:
        raise LookupError("paciente nao encontrado nesta clinica")

    odontograma = _odontograma_de(sessao, paciente_id, numero)

    dentes: dict[str, dict] = {
        str(fdi): {
            "raizes": numero_de_raizes(fdi),
            "canais": [r.value for r in canais_do_dente(fdi)],
            "canais_tela": [r.value for r in canais_em_ordem_de_tela(fdi)],
            "paredes": {p.value: r.value for p, r in paredes_do_dente(fdi).items()},
            "anterior": e_anterior(fdi),
            "regioes": {},
            "dente_inteiro": None,
            "condicoes": [],
        }
        for fdi in TODOS_FDI
    }
    boca: list[dict] = []

    linhas = sessao.execute(
        select(Lancamento, Procedimento.nome)
        .join(Procedimento, Lancamento.procedimento_id == Procedimento.id)
        .where(
            Lancamento.odontograma_id == odontograma.id,
            Lancamento.excluido_em.is_(None),
        )
    ).all()
    ids = [lancamento.id for lancamento, _ in linhas]
    regioes_por_lancamento: dict[int, list[str]] = {}
    if ids:
        for ligacao in sessao.scalars(
            select(LancamentoRegiao).where(LancamentoRegiao.lancamento_id.in_(ids))
        ):
            regioes_por_lancamento.setdefault(ligacao.lancamento_id, []).append(
                ligacao.regiao.value
            )

    def mais_forte(atual: str | None, novo: str) -> str:
        return novo if atual is None or FORCA[novo] > FORCA[atual] else atual

    for lancamento, nome_procedimento in linhas:
        estado = lancamento.status.value
        if lancamento.escopo is Escopo.BOCA:
            boca.append(
                {
                    "lancamento_id": lancamento.id,
                    "procedimento": nome_procedimento,
                    "status": estado,
                }
            )
            continue
        chave = str(lancamento.dente)
        if chave not in dentes:
            continue
        if lancamento.escopo is Escopo.DENTE:
            dentes[chave]["dente_inteiro"] = mais_forte(
                dentes[chave]["dente_inteiro"], estado
            )
            continue
        for regiao in regioes_por_lancamento.get(lancamento.id, []):
            dentes[chave]["regioes"][regiao] = mais_forte(
                dentes[chave]["regioes"].get(regiao), estado
            )

    for condicao in sessao.scalars(
        select(Condicao).where(
            Condicao.odontograma_id == odontograma.id, Condicao.excluido_em.is_(None)
        )
    ):
        chave = str(condicao.dente)
        if chave not in dentes:
            continue
        if condicao.icone_legado:
            dentes[chave]["condicoes"].append(condicao.icone_legado)
        for regiao in condicao.regioes or []:
            dentes[chave]["regioes"][regiao.value] = mais_forte(
                dentes[chave]["regioes"].get(regiao.value), "EXISTENTE"
            )

    return {
        "paciente": {
            "id": paciente.id,
            "nome": paciente.nome,
            "codigo_legado": paciente.codigo_legado,
        },
        "odontograma": {"id": odontograma.id, "numero": odontograma.numero},
        "dentes": dentes,
        "boca": boca,
    }


def historico(
    sessao: Session, *, clinica_id: int, paciente_id: int, limite: int = 200
) -> list[dict]:
    linhas = sessao.execute(
        select(Lancamento, Procedimento.nome)
        .join(Odontograma, Lancamento.odontograma_id == Odontograma.id)
        .join(Procedimento, Lancamento.procedimento_id == Procedimento.id)
        .where(
            Odontograma.paciente_id == paciente_id,
            Lancamento.clinica_id == clinica_id,
            Lancamento.excluido_em.is_(None),
        )
        .limit(limite)
    ).all()

    itens = [
        {
            "lancamento_id": lancamento.id,
            "data": lancamento.data_realizada or lancamento.data_planejada,
            "dente": lancamento.dente,
            "escopo": lancamento.escopo.value,
            "procedimento": nome,
            "status": lancamento.status.value,
            "valor": str(lancamento.valor),
            "observacao": lancamento.observacao,
        }
        for lancamento, nome in linhas
    ]
    # Lancamento sem data nenhuma vai para o fim, nao para o topo. O date.min no
    # lugar do None e obrigatorio: com dois lancamentos sem data, comparar
    # None com None levanta TypeError e derruba a tela.
    return sorted(
        itens, key=lambda i: (i["data"] is not None, i["data"] or date.min), reverse=True
    )


def lancamentos_do_paciente(
    sessao: Session, *, clinica_id: int, paciente_id: int
) -> list[dict]:
    """Fronteira que o futuro modulo financeiro vai consumir."""
    return historico(sessao, clinica_id=clinica_id, paciente_id=paciente_id, limite=10_000)


def anamnese(sessao: Session, *, clinica_id: int, paciente_id: int) -> list[dict]:
    perguntas = list(
        sessao.scalars(
            select(PerguntaAnamnese)
            .where(
                PerguntaAnamnese.clinica_id == clinica_id,
                PerguntaAnamnese.ativa.is_(True),
            )
            .order_by(PerguntaAnamnese.ordem, PerguntaAnamnese.codigo)
        )
    )
    respostas = {
        r.pergunta_id: r
        for r in sessao.scalars(
            select(RespostaAnamnese).where(RespostaAnamnese.paciente_id == paciente_id)
        )
    }
    return [
        {
            "pergunta_id": p.id,
            "codigo": p.codigo,
            "texto": p.texto,
            "tipo_resposta": p.tipo_resposta,
            "resposta": respostas[p.id].resposta if p.id in respostas else None,
            "respondido_em": respostas[p.id].respondido_em if p.id in respostas else None,
        }
        for p in perguntas
    ]


def responder(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    paciente_id: int,
    respostas: dict[int, str],
) -> int:
    """Grava as respostas preenchidas. Devolve quantas gravou.

    Resposta em branco nao cria linha: nao respondido e diferente de respondido
    com vazio, e a ficha de saude precisa distinguir os dois.
    """
    guardadas = {
        r.pergunta_id: r
        for r in sessao.scalars(
            select(RespostaAnamnese).where(RespostaAnamnese.paciente_id == paciente_id)
        )
    }
    gravadas = 0
    for pergunta_id, texto in respostas.items():
        limpo = (texto or "").strip()
        if not limpo:
            continue
        existente = guardadas.get(pergunta_id)
        antes = {"resposta": existente.resposta} if existente else None
        if existente is None:
            existente = RespostaAnamnese(
                paciente_id=paciente_id, pergunta_id=pergunta_id, resposta=limpo
            )
            sessao.add(existente)
        else:
            existente.resposta = limpo
        existente.respondido_em = date.today()
        sessao.flush()
        registrar(
            sessao,
            clinica_id=clinica_id,
            usuario_id=usuario_id,
            acao="CRIAR" if antes is None else "ATUALIZAR",
            entidade="resposta_anamnese",
            entidade_id=existente.id,
            antes=antes,
            depois={"pergunta_id": pergunta_id, "resposta": limpo},
        )
        gravadas += 1
    sessao.flush()
    return gravadas
