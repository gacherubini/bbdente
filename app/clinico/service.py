"""Fronteira publica do modulo clinico.

Quando o modulo financeiro chegar, ele chama funcoes daqui — nunca consulta a
tabela lancamento direto.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
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


def _boca_vazia() -> dict[str, dict]:
    """Os 32 dentes sem nada pintado, ja com a anatomia que o desenho precisa.

    O JavaScript nao sabe anatomia (AGENTS.md): paredes e canais saem daqui
    prontos. Esta e a base tanto do odontograma gravado quanto da previa.
    """
    return {
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


def _mais_forte(atual: str | None, novo: str) -> str:
    return novo if atual is None or FORCA[novo] > FORCA[atual] else atual


def _pintar(
    dentes: dict[str, dict],
    boca: list[dict],
    *,
    escopo: Escopo,
    dente: int | None,
    regioes: list[str],
    status: str,
    procedimento: str,
    lancamento_id: int | None = None,
) -> None:
    """Poe um tratamento no desenho. So mexe nos dicionarios que recebe.

    Gravado ou ainda por gravar passa por aqui — a regra de qual cor vence nao
    pode existir em dois lugares.
    """
    if escopo is Escopo.BOCA:
        boca.append(
            {
                "lancamento_id": lancamento_id,
                "procedimento": procedimento,
                "status": status,
            }
        )
        return
    chave = str(dente)
    if chave not in dentes:
        return
    if escopo is Escopo.DENTE:
        dentes[chave]["dente_inteiro"] = _mais_forte(
            dentes[chave]["dente_inteiro"], status
        )
        return
    for regiao in regioes:
        dentes[chave]["regioes"][regiao] = _mais_forte(
            dentes[chave]["regioes"].get(regiao), status
        )


def estado_do_odontograma(
    sessao: Session, *, clinica_id: int, paciente_id: int, numero: int = 1
) -> dict:
    # Fronteira de modulo: clinico nao consulta a tabela paciente, pergunta ao
    # service de pacientes.
    paciente = obter_paciente(sessao, clinica_id=clinica_id, paciente_id=paciente_id)
    if paciente is None:
        raise LookupError("paciente nao encontrado nesta clinica")

    odontograma = _odontograma_de(sessao, paciente_id, numero)

    dentes = _boca_vazia()
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

    for lancamento, nome_procedimento in linhas:
        _pintar(
            dentes,
            boca,
            escopo=lancamento.escopo,
            dente=lancamento.dente,
            regioes=regioes_por_lancamento.get(lancamento.id, []),
            status=lancamento.status.value,
            procedimento=nome_procedimento,
            lancamento_id=lancamento.id,
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
            dentes[chave]["regioes"][regiao.value] = _mais_forte(
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


@dataclass(frozen=True)
class ItemAtendimento:
    """Um tratamento do atendimento antes de existir no banco.

    E o que a tela em branco acumula enquanto ainda nao se sabe de quem e o
    atendimento. Mesmos campos de `lancar`, sem `paciente_id` — que e justamente
    o que falta ate o fim.
    """

    procedimento_id: int
    escopo: Escopo
    status: StatusLancamento
    dente: int | None = None
    regioes: tuple[Regiao, ...] = ()
    data: date | None = None
    valor: Decimal | None = None
    observacao: str | None = None


def _nomes_de_procedimento(
    sessao: Session, *, clinica_id: int, ids: Iterable[int]
) -> dict[int, str]:
    """Confere que todo tratamento citado existe NESTA clinica, e traz o nome."""
    pedidos = set(ids)
    if not pedidos:
        return {}
    nomes = dict(
        sessao.execute(
            select(Procedimento.id, Procedimento.nome).where(
                Procedimento.id.in_(pedidos), Procedimento.clinica_id == clinica_id
            )
        ).all()
    )
    faltando = pedidos - nomes.keys()
    if faltando:
        raise LookupError(
            f"tratamento nao encontrado nesta clinica: {sorted(faltando)[0]}"
        )
    return nomes


def estado_vazio() -> dict:
    """A boca em branco: 32 dentes, ninguem dentro, nada gravado."""
    return {
        "paciente": None,
        "odontograma": {"id": None, "numero": 1},
        "dentes": _boca_vazia(),
        "boca": [],
    }


def estado_de_previa(
    sessao: Session, *, clinica_id: int, itens: "list[ItemAtendimento]"
) -> dict:
    """Pinta um atendimento que ainda nao foi gravado. NAO escreve nada.

    Existe para a regra de qual cor vence morar so no servidor, onde tem teste,
    em vez de ser copiada para o JavaScript.
    """
    nomes = _nomes_de_procedimento(
        sessao, clinica_id=clinica_id, ids=[item.procedimento_id for item in itens]
    )
    estado = estado_vazio()
    for item in itens:
        _validar(item.escopo, item.dente, list(item.regioes))
        _pintar(
            estado["dentes"],
            estado["boca"],
            escopo=item.escopo,
            dente=item.dente,
            regioes=[regiao.value for regiao in item.regioes],
            status=item.status.value,
            procedimento=nomes[item.procedimento_id],
        )
    return estado


def validar_atendimento(
    sessao: Session, *, clinica_id: int, itens: "list[ItemAtendimento]"
) -> None:
    """Recusa o atendimento inteiro ANTES de qualquer escrita.

    Existe separada de `lancar_atendimento` para quem chama poder conferir tudo
    antes de criar o cadastro do paciente: assim um item errado nao deixa para
    tras um paciente novo que so existia para receber esse atendimento.
    """
    if not itens:
        raise EscopoInvalido("atendimento sem tratamento nenhum")
    _nomes_de_procedimento(
        sessao, clinica_id=clinica_id, ids=[item.procedimento_id for item in itens]
    )
    for item in itens:
        _validar(item.escopo, item.dente, list(item.regioes))


def lancar_atendimento(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    paciente_id: int,
    itens: "list[ItemAtendimento]",
    numero_odontograma: int = 1,
) -> list[Lancamento]:
    """Grava o atendimento inteiro de uma vez, no fim, quando ja se sabe de quem e.

    Valida TUDO antes de escrever a primeira linha: ou entra o atendimento
    completo, ou nao entra nada. Meio atendimento gravado seria pior que nenhum,
    porque ninguem saberia qual metade faltou.
    """
    validar_atendimento(sessao, clinica_id=clinica_id, itens=itens)

    return [
        lancar(
            sessao,
            clinica_id=clinica_id,
            usuario_id=usuario_id,
            paciente_id=paciente_id,
            procedimento_id=item.procedimento_id,
            escopo=item.escopo,
            dente=item.dente,
            regioes=list(item.regioes),
            status=item.status,
            data=item.data,
            valor=item.valor,
            observacao=item.observacao,
            numero_odontograma=numero_odontograma,
        )
        for item in itens
    ]


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


def editar_lancamento(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    lancamento_id: int,
    status: StatusLancamento,
    data: date | None = None,
    valor: Decimal | None = None,
    observacao: str | None = None,
) -> Lancamento:
    """Corrige um lancamento existente: situacao, data, valor e observacao.

    NAO mexe em dente, regiao nem procedimento. Trocar o alvo de um tratamento
    nao e correcao, e outro tratamento — para isso existe excluir (logicamente) e
    lancar de novo, que deixa os dois lados na auditoria.

    A data e uma so por vez: planejado guarda `data_planejada`, realizado guarda
    `data_realizada`. Guardar as duas seria guardar uma contradicao.
    """
    if valor is not None and valor < 0:
        raise EscopoInvalido("valor nao pode ser negativo")

    lancamento = sessao.scalars(
        select(Lancamento).where(
            Lancamento.id == lancamento_id,
            Lancamento.clinica_id == clinica_id,
            Lancamento.excluido_em.is_(None),
        )
    ).first()
    if lancamento is None:
        raise LookupError("lancamento nao encontrado")

    antes = {
        "status": lancamento.status.value,
        "valor": str(lancamento.valor),
        "data": (
            lancamento.data_realizada or lancamento.data_planejada
        ).isoformat()
        if (lancamento.data_realizada or lancamento.data_planejada)
        else None,
        "observacao": lancamento.observacao,
    }

    realizado = status is StatusLancamento.REALIZADO
    lancamento.status = status
    lancamento.data_planejada = None if realizado else data
    lancamento.data_realizada = data if realizado else None
    if valor is not None:
        lancamento.valor = valor.quantize(Decimal("0.01"))
    lancamento.observacao = observacao
    sessao.flush()

    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="ATUALIZAR",
        entidade="lancamento",
        entidade_id=lancamento.id,
        antes=antes,
        depois={
            "status": status.value,
            "valor": str(lancamento.valor),
            "data": data.isoformat() if data else None,
            "observacao": observacao,
        },
    )
    return lancamento


# --- producao: o que o financeiro pergunta a este modulo -----------------------
#
# O modulo financeiro nunca consulta `lancamento` direto. Estas funcoes sao a
# fronteira que ele usa, e cada uma resolve tudo numa consulta agregada — sao
# 44.812 lancamentos, e um laco em Python sobre eles derruba a tela.


def _realizados_no_periodo(clinica_id: int, de: date, ate: date):
    return (
        Lancamento.clinica_id == clinica_id,
        Lancamento.status == StatusLancamento.REALIZADO,
        Lancamento.excluido_em.is_(None),
        Lancamento.data_realizada >= de,
        Lancamento.data_realizada <= ate,
    )


def producao(sessao: Session, *, clinica_id: int, de: date, ate: date) -> dict:
    """Quanto de tratamento foi FEITO no periodo, e quantos foram.

    Planejado nao entra: produzido e o que aconteceu, nao o que foi prometido.
    """
    soma, quantos = sessao.execute(
        select(
            func.coalesce(func.sum(Lancamento.valor), 0), func.count(Lancamento.id)
        ).where(*_realizados_no_periodo(clinica_id, de, ate))
    ).one()
    return {
        "valor": Decimal(soma).quantize(Decimal("0.01")),
        "tratamentos": quantos,
    }


def producao_por_dia(
    sessao: Session, *, clinica_id: int, de: date, ate: date
) -> dict[date, int]:
    """Quantos tratamentos foram feitos em cada dia do periodo."""
    return {
        dia: quantos
        for dia, quantos in sessao.execute(
            select(Lancamento.data_realizada, func.count(Lancamento.id))
            .where(*_realizados_no_periodo(clinica_id, de, ate))
            .group_by(Lancamento.data_realizada)
        ).all()
    }


def producao_por_procedimento(
    sessao: Session, *, clinica_id: int, de: date, ate: date
) -> dict[int, Decimal]:
    """Quanto cada tratamento rendeu no periodo, por id de procedimento.

    Devolve id, nao nome de categoria: quem sabe a que categoria um procedimento
    pertence e o catalogo, e perguntar a ele preserva a fronteira.
    """
    return {
        procedimento_id: Decimal(soma).quantize(Decimal("0.01"))
        for procedimento_id, soma in sessao.execute(
            select(
                Lancamento.procedimento_id, func.coalesce(func.sum(Lancamento.valor), 0)
            )
            .where(*_realizados_no_periodo(clinica_id, de, ate))
            .group_by(Lancamento.procedimento_id)
        ).all()
    }


def producao_por_paciente(
    sessao: Session, *, clinica_id: int, de: date, ate: date
) -> dict[int, Decimal]:
    """Quanto cada paciente teve de tratamento feito no periodo.

    Devolve id, nao convenio: quem sabe o convenio de um paciente e o modulo
    pacientes.
    """
    return {
        paciente_id: Decimal(soma).quantize(Decimal("0.01"))
        for paciente_id, soma in sessao.execute(
            select(
                Odontograma.paciente_id, func.coalesce(func.sum(Lancamento.valor), 0)
            )
            .join(Odontograma, Lancamento.odontograma_id == Odontograma.id)
            .where(*_realizados_no_periodo(clinica_id, de, ate))
            .group_by(Odontograma.paciente_id)
        ).all()
    }
