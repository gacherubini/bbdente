"""Fronteira publica do modulo pacientes."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.auth.auditoria import registrar
from app.catalogo.service import nomes_de_convenio
from app.pacientes.models import Paciente, PacienteTelefone
from app.pacientes.telefone import formatar, parecer_incompleto, parecer_longo, separar

# "Ativo" = veio nos ultimos 4 anos. Sao 494 dos 5.561 no banco real.
ANOS_PARA_SER_ATIVO = 4
LIMITE_PADRAO = 100


class Filtro(StrEnum):
    ATIVOS = "ativos"
    COM_PENDENCIA = "com_pendencia"
    EM_ABERTO = "em_aberto"
    TODOS = "todos"


@dataclass
class LinhaPaciente:
    id: int
    nome: str
    codigo_legado: str | None
    idade: int | None
    telefone: str | None
    telefone_suspeito: bool
    ultimo_atendimento: date | None
    data_suspeita: bool
    convenio: str | None
    pendentes: int
    em_aberto: Decimal
    revisar_motivo: list[str] = field(default_factory=list)


def _idade(nascimento: date | None) -> int | None:
    if nascimento is None:
        return None
    hoje = date.today()
    return (
        hoje.year
        - nascimento.year
        - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
    )


def _corte_de_atividade() -> date:
    hoje = date.today()
    try:
        return hoje.replace(year=hoje.year - ANOS_PARA_SER_ATIVO)
    except ValueError:
        # 29 de fevereiro: o ano de 4 anos atras pode nao ter o dia 29.
        return hoje.replace(year=hoje.year - ANOS_PARA_SER_ATIVO, day=28)


def obter(sessao: Session, *, clinica_id: int, paciente_id: int) -> Paciente | None:
    return sessao.scalars(
        select(Paciente).where(
            Paciente.id == paciente_id,
            Paciente.clinica_id == clinica_id,
            Paciente.excluido_em.is_(None),
        )
    ).first()


def contagens(sessao: Session, *, clinica_id: int) -> dict[str, int]:
    """Numeros do cabecalho. Tres agregacoes no banco — nunca carregando a base.

    A versao ingenua chamaria buscar() e contaria em Python: com 5.561 pacientes
    isso seria uma varredura completa a cada abertura da tela.
    """
    from app.clinico.service import contar_pacientes_com_pendencia

    base = select(func.count()).select_from(Paciente).where(
        Paciente.clinica_id == clinica_id, Paciente.excluido_em.is_(None)
    )
    return {
        "total": sessao.scalars(base).one(),
        "ativos": sessao.scalars(
            base.where(Paciente.ultimo_atendimento >= _corte_de_atividade())
        ).one(),
        "com_pendencia": contar_pacientes_com_pendencia(sessao, clinica_id=clinica_id),
    }


def _montar_linhas(
    sessao: Session, *, clinica_id: int, pacientes: "Iterable[Paciente]"
) -> list[LinhaPaciente]:
    """Transforma Paciente em LinhaPaciente para a tela — uma consulta de resumo e
    uma de convenios para o lote inteiro, nunca uma por paciente. Compartilhado por
    buscar() e semelhantes() para as duas telas mostrarem a mesma linha."""
    # Import aqui dentro, nao no topo: clinico.service importa pacientes.service,
    # e importar nos dois sentidos no topo trava o Python com import circular.
    from app.clinico.service import resumo_por_paciente

    pacientes = list(pacientes)
    resumo = resumo_por_paciente(
        sessao, clinica_id=clinica_id, paciente_ids=[p.id for p in pacientes]
    )
    convenios = nomes_de_convenio(
        sessao,
        clinica_id=clinica_id,
        convenio_ids={p.convenio_id for p in pacientes if p.convenio_id},
    )

    linhas: list[LinhaPaciente] = []
    for paciente in pacientes:
        pendentes, em_aberto = resumo.get(paciente.id, (0, Decimal("0.00")))
        principal = next(
            (t for t in paciente.telefones if t.principal), None
        ) or next(iter(paciente.telefones), None)

        linhas.append(
            LinhaPaciente(
                id=paciente.id,
                nome=paciente.nome,
                codigo_legado=paciente.codigo_legado,
                idade=_idade(paciente.nascimento),
                telefone=formatar(principal.numero) if principal else None,
                telefone_suspeito=bool(principal)
                and parecer_incompleto(principal.numero),
                ultimo_atendimento=paciente.ultimo_atendimento,
                data_suspeita="data_suspeita" in (paciente.revisar_motivo or []),
                convenio=convenios.get(paciente.convenio_id),
                pendentes=pendentes,
                em_aberto=em_aberto,
                revisar_motivo=list(paciente.revisar_motivo or []),
            )
        )
    return linhas


def buscar(
    sessao: Session,
    *,
    clinica_id: int,
    termo: str = "",
    filtro: Filtro = Filtro.ATIVOS,
    limite: int | None = LIMITE_PADRAO,
) -> list[LinhaPaciente]:
    consulta = (
        select(Paciente)
        .options(selectinload(Paciente.telefones))
        .where(Paciente.clinica_id == clinica_id, Paciente.excluido_em.is_(None))
        .order_by(Paciente.nome)
    )

    termo = (termo or "").strip()
    if termo:
        padrao = f"%{termo}%"
        so_digitos = "".join(c for c in termo if c.isdigit())
        condicoes = [Paciente.nome.ilike(padrao), Paciente.codigo_legado.ilike(padrao)]
        if so_digitos:
            condicoes.append(
                Paciente.id.in_(
                    select(PacienteTelefone.paciente_id).where(
                        PacienteTelefone.numero.like(f"%{so_digitos}%")
                    )
                )
            )
        consulta = consulta.where(or_(*condicoes))
    elif filtro is Filtro.ATIVOS:
        consulta = consulta.where(Paciente.ultimo_atendimento >= _corte_de_atividade())

    # COM_PENDENCIA e EM_ABERTO sao peneirados em Python depois da consulta, entao
    # trazemos uma folga do banco para o limite final ainda poder ser preenchido.
    if limite is not None:
        folga = limite * 10 if filtro in (Filtro.COM_PENDENCIA, Filtro.EM_ABERTO) else limite
        consulta = consulta.limit(folga)

    linhas = _montar_linhas(sessao, clinica_id=clinica_id, pacientes=sessao.scalars(consulta))
    if filtro is Filtro.COM_PENDENCIA:
        linhas = [linha for linha in linhas if linha.pendentes]
    elif filtro is Filtro.EM_ABERTO:
        linhas = [linha for linha in linhas if linha.em_aberto > 0]
    if limite is not None:
        return linhas[:limite]
    return linhas


# Tira o acento no proprio Postgres, sem depender da extensao unaccent (que exige
# CREATE EXTENSION, ou seja, uma migration e permissao de superusuario no servidor).
_COM_ACENTO = "ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇÑáàâãäéèêëíìîïóòôõöúùûüçñ"
_SEM_ACENTO = "AAAAAEEEEIIIIOOOOOUUUUCNaaaaaeeeeiiiiooooouuuucn"
_TABELA_SEM_ACENTO = str.maketrans(_COM_ACENTO, _SEM_ACENTO)


def _normalizar(nome: str) -> str:
    """'  maria  sílva ' -> 'MARIA SILVA'. Mesma regra do lado do banco."""
    return " ".join(nome.translate(_TABELA_SEM_ACENTO).upper().split())


def _nome_normalizado(coluna):
    """A mesma normalizacao de _normalizar(), escrita em SQL."""
    return func.regexp_replace(
        func.btrim(func.upper(func.translate(coluna, _COM_ACENTO, _SEM_ACENTO))),
        r"\s+",
        " ",
        "g",
    )


def semelhantes(
    sessao: Session, *, clinica_id: int, nome: str, limite: int = 5
) -> list[LinhaPaciente]:
    """Cadastros que sao provavelmente a MESMA pessoa, para a tela avisar antes de
    criar duplicata. Nunca traz excluido nem outra clinica.

    Duas regras, as duas exatas (nunca por pedaco solto do nome):

    1. nome normalizado igual — sem acento, sem diferenca de caixa, espaco repetido
       colapsado: 'maria  sílva' encontra 'MARIA SILVA';
    2. mesmo primeiro nome E mesmo ultimo sobrenome: 'MARIA SILVA' encontra
       'MARIA DA SILVA', que e a mesma pessoa com a particula digitada. Nao encontra
       'MARIA SANTOS' nem 'MARIA SILVA SANTOS' — sobrenome final diferente e, na
       pratica, outra pessoa.

    Casar por pedaco ('%MARIA%') foi tentado e reprovado contra os 5.561 nomes
    reais: 'MARIA' trazia 'ADEMAR BITENCOURT' e, pior, com 404 nomes contendo
    'MARIA' o limite cortava em ordem alfabetica ANTES da duplicata verdadeira — a
    tela avisava a pessoa errada e calava sobre a certa. Com regra exata o limite
    nao esconde mais nada; quem digita so o primeiro nome ve pouco ou nada, que e o
    certo: o aviso existe para o caso claro.

    Custo: as duas regras calculam a normalizacao linha a linha, entao o Postgres
    varre a tabela de pacientes (5.561 linhas, alguns milissegundos). Aceitavel
    porque isto roda uma vez por cadastro, nao a cada tecla. Se um dia rodar a cada
    tecla, o caminho e uma coluna gerada com essa mesma expressao mais um indice —
    custa uma migration e um pouco de disco, e nao muda esta funcao.
    """
    alvo = _normalizar(nome or "")
    if not alvo:
        return []
    partes = alvo.split(" ")
    primeiro, ultimo = partes[0], partes[-1]
    normalizado = _nome_normalizado(Paciente.nome)

    consulta = (
        select(Paciente)
        .options(selectinload(Paciente.telefones))
        .where(
            Paciente.clinica_id == clinica_id,
            Paciente.excluido_em.is_(None),
            or_(
                normalizado == alvo,
                and_(
                    func.split_part(normalizado, " ", 1) == primeiro,
                    # Tudo ate o ultimo espaco fora: sobra o ultimo sobrenome. Nome
                    # de uma palavra so nao tem espaco e volta inteiro.
                    func.regexp_replace(normalizado, r".*\s", "") == ultimo,
                ),
            ),
        )
        .order_by(Paciente.nome)
        .limit(limite)
    )
    return _montar_linhas(
        sessao, clinica_id=clinica_id, pacientes=sessao.scalars(consulta)
    )


# As marcas que a tela de edicao sabe conferir — e portanto as unicas que ela pode
# tirar. Marca de outra origem (`cadastro_so_no_orcamento`, `paciente_perdido`)
# continua intocada: quem nao sabe verificar nao apaga.
MARCAS_DE_TELEFONE = ("telefone_incompleto", "telefone_suspeito")


def _gravar_telefones(
    sessao: Session, *, paciente: Paciente, bruto: str
) -> list[str]:
    """Poe no cadastro exatamente os numeros que vieram no texto, e devolve as
    marcas de revisao que eles merecem.

    Numero que ja estava fica como esta; numero que saiu do texto e marcado com
    `excluido_em`, nunca apagado — pode ser a unica forma de achar alguem que
    nao volta ha vinte anos. A regua e a MESMA da migracao: numero estranho entra
    marcado, jamais corrigido no chute nem recusado.
    """
    pedidos: list[str] = []
    for numero in separar(bruto):
        if numero not in pedidos:
            pedidos.append(numero)

    vivos = {t.numero: t for t in paciente.telefones}
    for numero, telefone in vivos.items():
        if numero not in pedidos:
            telefone.excluido_em = datetime.now(UTC)

    for posicao, numero in enumerate(pedidos):
        atual = vivos.get(numero)
        if atual is not None:
            atual.principal = posicao == 0
            continue
        sessao.add(
            PacienteTelefone(
                paciente_id=paciente.id,
                numero=numero,
                # O texto cru como foi digitado, caso a separacao erre.
                numero_original=bruto,
                principal=posicao == 0,
            )
        )
    sessao.flush()
    # As linhas novas foram inseridas por `paciente_id`, nao anexadas a colecao:
    # sem expirar, quem ler `paciente.telefones` depois — inclusive uma consulta
    # nova, que nao sobrescreve atributo ja carregado — enxerga a lista velha.
    sessao.expire(paciente, ["telefones"])

    motivos: list[str] = []
    for numero in pedidos:
        if parecer_incompleto(numero) and "telefone_incompleto" not in motivos:
            motivos.append("telefone_incompleto")
        if parecer_longo(numero) and "telefone_suspeito" not in motivos:
            motivos.append("telefone_suspeito")
    return motivos


def criar(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    nome: str,
    telefone: str | None = None,
    nascimento: date | None = None,
    convenio_id: int | None = None,
) -> Paciente:
    """Cadastra um paciente novo. Faz flush (o chamador precisa do id), nunca commit —
    quem chama decide gravar.

    O telefone passa pelo MESMO separador da migracao e recebe as MESMAS marcacoes:
    cadastro novo e historico antigo tem de ter uma regua so, senao a lista de
    'revisar' significaria coisas diferentes conforme a origem do dado. Como la,
    numero estranho entra marcado — nunca corrigido no chute nem recusado.
    """
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("o nome do paciente e obrigatorio")

    paciente = Paciente(
        clinica_id=clinica_id,
        # Paciente novo nao tem codigo do Dentalis: codigo_legado so existe no
        # historico migrado.
        codigo_legado=None,
        nome=nome,
        nascimento=nascimento,
        convenio_id=convenio_id,
        cadastrado_em=date.today(),
        revisar_motivo=[],
    )
    sessao.add(paciente)
    sessao.flush()

    bruto = (telefone or "").strip()
    motivos = _gravar_telefones(sessao, paciente=paciente, bruto=bruto)
    if motivos:
        paciente.revisar_motivo = motivos
    sessao.flush()

    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="CRIAR",
        entidade="paciente",
        entidade_id=paciente.id,
        depois={
            "nome": nome,
            "nascimento": nascimento.isoformat() if nascimento else None,
            "convenio_id": convenio_id,
            "telefone": bruto or None,
        },
    )
    return paciente


def atualizar(
    sessao: Session,
    *,
    clinica_id: int,
    usuario_id: int,
    paciente_id: int,
    nome: str,
    telefone: str | None = None,
    nascimento: date | None = None,
    convenio_id: int | None = None,
) -> Paciente:
    """Corrige o cadastro. Faz flush, nunca commit — quem chama decide gravar.

    O `codigo_legado` NAO entra: e a chave que liga este cadastro aos 30 anos de
    historico do Dentalis, e editar seria cortar o fio.

    Corrigir tira a marca: cadastro que estava marcado como telefone incompleto e
    ganhou um numero bom perde a marca, e a lista de 'revisar' encolhe com o
    trabalho da recepcao. So saem as marcas que esta funcao sabe conferir.
    """
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("o nome do paciente e obrigatorio")

    paciente = obter(sessao, clinica_id=clinica_id, paciente_id=paciente_id)
    if paciente is None:
        raise LookupError("paciente nao encontrado nesta clinica")

    antes = {
        "nome": paciente.nome,
        "nascimento": paciente.nascimento.isoformat() if paciente.nascimento else None,
        "convenio_id": paciente.convenio_id,
        "telefone": ", ".join(t.numero for t in paciente.telefones) or None,
    }

    paciente.nome = nome
    paciente.nascimento = nascimento
    paciente.convenio_id = convenio_id

    bruto = (telefone or "").strip()
    marcas = _gravar_telefones(sessao, paciente=paciente, bruto=bruto)
    outras = [m for m in paciente.revisar_motivo if m not in MARCAS_DE_TELEFONE]
    paciente.revisar_motivo = outras + marcas
    sessao.flush()

    registrar(
        sessao,
        clinica_id=clinica_id,
        usuario_id=usuario_id,
        acao="ATUALIZAR",
        entidade="paciente",
        entidade_id=paciente.id,
        antes=antes,
        depois={
            "nome": nome,
            "nascimento": nascimento.isoformat() if nascimento else None,
            "convenio_id": convenio_id,
            "telefone": bruto or None,
        },
    )
    return paciente


def convenios_de(
    sessao: Session, *, clinica_id: int, paciente_ids: Iterable[int]
) -> dict[int, int | None]:
    """O convenio de cada paciente. Uma consulta para a lista inteira."""
    ids = list(paciente_ids)
    if not ids:
        return {}
    return {
        paciente_id: convenio_id
        for paciente_id, convenio_id in sessao.execute(
            select(Paciente.id, Paciente.convenio_id).where(
                Paciente.id.in_(ids), Paciente.clinica_id == clinica_id
            )
        ).all()
    }


def nomes_de(
    sessao: Session, *, clinica_id: int, paciente_ids: Iterable[int]
) -> dict[int, str]:
    """O nome de cada paciente. Uma consulta para a lista inteira — a lista de
    cobranca tem milhares de linhas, e uma consulta por linha trava a tela."""
    ids = list(paciente_ids)
    if not ids:
        return {}
    return {
        paciente_id: nome
        for paciente_id, nome in sessao.execute(
            select(Paciente.id, Paciente.nome).where(
                Paciente.id.in_(ids), Paciente.clinica_id == clinica_id
            )
        ).all()
    }
