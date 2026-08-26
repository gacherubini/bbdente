"""Migra o questionario de saude: 37 perguntas, 2.046 respostas, 80 observacoes.

As respostas vivem em duas tabelas no legado — ARQSINAO ('S'/'N') e ARQSIQUA
(texto). Aqui viram uma so; o tipo da pergunta continua em tipo_resposta.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clinico.models import ObservacaoClinica, PerguntaAnamnese, RespostaAnamnese
from app.pacientes.models import Paciente
from migracao.extrato import Extrato
from migracao.texto import limpar


@dataclass
class ResultadoAnamnese:
    perguntas: int = 0
    respostas: int = 0
    observacoes: int = 0


def migrar(sessao: Session, extrato: Extrato, clinica_id: int) -> ResultadoAnamnese:
    resultado = ResultadoAnamnese()

    perguntas = {
        p.codigo: p
        for p in sessao.scalars(
            select(PerguntaAnamnese).where(PerguntaAnamnese.clinica_id == clinica_id)
        )
    }
    for ordem, linha in enumerate(extrato.linhas("ARQUEST", ordem="NUMQUEST")):
        codigo = (limpar(linha["NUMQUEST"]) or "").zfill(2)
        texto = " ".join(
            parte
            for parte in (
                limpar(linha["DESCRICAO"]), limpar(linha["DESCRI2"]), limpar(linha["DESCRI3"])
            )
            if parte
        )
        if codigo in perguntas:
            perguntas[codigo].texto = texto or perguntas[codigo].texto
        else:
            pergunta = PerguntaAnamnese(
                clinica_id=clinica_id,
                codigo=codigo,
                texto=texto or f"Pergunta {codigo}",
                tipo_resposta=int(float(linha["TIPORESP"] or 1)),
                ordem=ordem,
            )
            sessao.add(pergunta)
            perguntas[codigo] = pergunta
        resultado.perguntas += 1
    sessao.flush()

    pacientes = {
        p.codigo_legado: p.id
        for p in sessao.scalars(select(Paciente).where(Paciente.clinica_id == clinica_id))
    }
    ja_respondidas = {
        (r.paciente_id, r.pergunta_id) for r in sessao.scalars(select(RespostaAnamnese))
    }

    for tabela in ("ARQSINAO", "ARQSIQUA"):
        for linha in extrato.linhas(tabela):
            paciente_id = pacientes.get(limpar(linha["CODICLIE"]))
            pergunta = perguntas.get((limpar(linha["NUMQUEST"]) or "").zfill(2))
            if paciente_id is None or pergunta is None:
                continue
            chave = (paciente_id, pergunta.id)
            if chave in ja_respondidas:
                resultado.respostas += 1
                continue
            sessao.add(
                RespostaAnamnese(
                    paciente_id=paciente_id,
                    pergunta_id=pergunta.id,
                    resposta=limpar(linha["RESP"]) or "",
                )
            )
            ja_respondidas.add(chave)
            resultado.respostas += 1
    sessao.flush()

    if sessao.query(ObservacaoClinica).count() == 0:
        for linha in extrato.linhas("OBSERCLI"):
            paciente_id = pacientes.get(limpar(linha["CODICLIE"]))
            texto = limpar(linha["OBS"])
            # ALERTA e um flag 'S'/'N' da tela antiga, com 1 unico 'S' em 1.481
            # linhas: sem significado recuperavel. Nao migra.
            if paciente_id is None or not texto:
                continue
            sessao.add(ObservacaoClinica(paciente_id=paciente_id, texto=texto))
            resultado.observacoes += 1
    else:
        resultado.observacoes = sessao.query(ObservacaoClinica).count()
    sessao.flush()

    return resultado
