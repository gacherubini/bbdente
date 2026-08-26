"""Migra os 44.812 lancamentos e as 29.350 regioes.

O ARQDENTE nao tem chave primaria propria. A identidade de um lancamento aqui e
(CODICLIE, NUMODO, NUMDENTE, CODSERV, DTSERV, ordem-na-leitura), gravada em
codigo_legado — e o que torna a migracao idempotente.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo.models import Categoria, Procedimento
from app.clinico.models import Lancamento, LancamentoRegiao, Odontograma
from app.pacientes.models import Paciente
from app.shared.tipos import Escopo, StatusLancamento
from migracao.extrato import Extrato
from migracao.posdente import decodificar
from migracao.texto import data_legada, limpar

# 'J' aparece em 14 registros, todos com valor zero e sem data de realizacao.
# Significado perdido junto com a interface do Dentalis: entra como planejado e marcado.
STATUS_LEGADO: dict[str, StatusLancamento] = {
    "R": StatusLancamento.REALIZADO,
    "E": StatusLancamento.PLANEJADO,
    "J": StatusLancamento.PLANEJADO,
}
CATEGORIA_PADRAO = "11"  # "Outros Servicos"


@dataclass
class ResultadoLancamentos:
    odontogramas: int = 0
    lancamentos: int = 0
    regioes: int = 0
    marcados: int = 0
    soma_valores: Decimal = field(default_factory=lambda: Decimal("0"))


def _valor(bruto) -> Decimal:
    try:
        return Decimal(str(bruto or 0)).quantize(Decimal("0.01"))
    except (TypeError, ArithmeticError):
        return Decimal("0.00")


def _procedimento_desconhecido(
    sessao: Session, clinica_id: int, codigo: str, categoria_id: int
) -> Procedimento:
    """CODSERV que nao existe em nenhuma tabela de preco. Sao 2 registros reais.
    Criar um procedimento provisorio preserva o lancamento; descartar perderia dado."""
    proc = Procedimento(
        clinica_id=clinica_id,
        codigo=codigo,
        nome=f"DESCONHECIDO (cod. {codigo})",
        categoria_id=categoria_id,
        ativo=False,
        escopo_sugerido=Escopo.DENTE,
        regioes_sugeridas=[],
    )
    sessao.add(proc)
    sessao.flush()
    return proc


def migrar(sessao: Session, extrato: Extrato, clinica_id: int) -> ResultadoLancamentos:
    resultado = ResultadoLancamentos()

    pacientes = {
        p.codigo_legado: p.id
        for p in sessao.scalars(select(Paciente).where(Paciente.clinica_id == clinica_id))
    }
    procedimentos = {
        p.codigo: p.id
        for p in sessao.scalars(
            select(Procedimento).where(Procedimento.clinica_id == clinica_id)
        )
    }
    categoria_padrao = sessao.scalars(
        select(Categoria).where(
            Categoria.clinica_id == clinica_id, Categoria.codigo == CATEGORIA_PADRAO
        )
    ).one().id

    odontogramas: dict[tuple[int, int], int] = {
        (o.paciente_id, o.numero): o.id for o in sessao.scalars(select(Odontograma))
    }
    ja_migrados = {
        codigo
        for (codigo,) in sessao.query(Lancamento.codigo_legado).filter(
            Lancamento.clinica_id == clinica_id, Lancamento.codigo_legado.isnot(None)
        )
    }

    for ordem, linha in enumerate(extrato.linhas("ARQDENTE")):
        codigo_paciente = limpar(linha["CODICLIE"])
        paciente_id = pacientes.get(codigo_paciente)
        if paciente_id is None:
            # O extrato ja provou ter zero referencias orfas; se aparecer uma, e
            # bug de codigo, nao dado ruim. Falha alto.
            raise ValueError(f"lancamento aponta para paciente inexistente: {codigo_paciente!r}")

        codigo_legado = f"{codigo_paciente}#{ordem}"
        if codigo_legado in ja_migrados:
            resultado.lancamentos += 1
            continue

        numero_odo = int(float(linha["NUMODO"] or 1)) or 1
        chave = (paciente_id, numero_odo)
        if chave not in odontogramas:
            odontograma = Odontograma(paciente_id=paciente_id, numero=numero_odo)
            sessao.add(odontograma)
            sessao.flush()
            odontogramas[chave] = odontograma.id
            resultado.odontogramas += 1

        alvo = decodificar(linha["NUMDENTE"], linha["POSDENTE"])
        motivos = list(alvo.motivos)

        cod_serv = (limpar(linha["CODSERV"]) or "").strip()
        procedimento_id = procedimentos.get(cod_serv)
        if procedimento_id is None:
            proc = _procedimento_desconhecido(
                sessao, clinica_id, cod_serv or "?", categoria_padrao
            )
            procedimentos[cod_serv] = proc.id
            procedimento_id = proc.id
            motivos.append("procedimento_desconhecido")

        situacao = (limpar(linha["SITUACAO"]) or "").upper()
        status = STATUS_LEGADO.get(situacao, StatusLancamento.PLANEJADO)
        if situacao not in ("R", "E"):
            motivos.append("situacao_desconhecida")

        planejada, motivo_p = data_legada(linha["DTSERV"])
        realizada, motivo_r = data_legada(linha["DTREAL"])
        for motivo in (motivo_p, motivo_r):
            if motivo and motivo not in motivos:
                motivos.append(motivo)

        valor = _valor(linha["CZSERV"])
        lancamento = Lancamento(
            clinica_id=clinica_id,
            odontograma_id=odontogramas[chave],
            dente=alvo.fdi,
            escopo=alvo.escopo,
            procedimento_id=procedimento_id,
            status=status,
            data_planejada=planejada,
            data_realizada=realizada,
            valor=valor,
            observacao=limpar(linha["OBSERV"]),
            codigo_legado=codigo_legado,
            revisar_motivo=motivos,
        )
        sessao.add(lancamento)
        sessao.flush()

        if alvo.regiao is not None:
            sessao.add(
                LancamentoRegiao(lancamento_id=lancamento.id, regiao=alvo.regiao)
            )
            resultado.regioes += 1

        resultado.lancamentos += 1
        resultado.soma_valores += valor
        if motivos:
            resultado.marcados += 1

        if resultado.lancamentos % 5_000 == 0:
            sessao.flush()

    sessao.flush()
    return resultado
