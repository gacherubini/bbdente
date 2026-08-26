"""Migra os 5.561 pacientes com telefones, enderecos e marcacoes de revisao.

Regra que atravessa o arquivo inteiro: dado ruim entra marcado, nunca corrigido no
chute nem descartado. A Dra. Katia decide o que fazer com cada marcacao.
"""

from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo.models import Convenio
from app.pacientes.models import Paciente, PacienteEndereco, PacienteTelefone
from app.pacientes.telefone import parecer_incompleto, separar
from migracao.extrato import Extrato
from migracao.texto import data_legada, limpar


@dataclass
class ResultadoPacientes:
    pacientes: int = 0
    telefones: int = 0
    enderecos: int = 0
    marcados: int = 0


def _duplicados_por_nome(extrato: Extrato) -> set[str]:
    """Nomes que aparecem em mais de um cadastro. Sao 2 no banco real."""
    contagem: Counter = Counter()
    for linha in extrato.linhas("ARQCLIEN"):
        nome = (limpar(linha["NOME"]) or "").upper()
        if nome:
            contagem[nome] += 1
    return {nome for nome, n in contagem.items() if n > 1}


def _endereco(
    paciente_id: int, tipo: str, linha: dict, campos: tuple[str, str, str, str, str]
) -> PacienteEndereco | None:
    logradouro, bairro, cidade, uf, cep = (limpar(linha.get(c)) for c in campos)
    if not any((logradouro, bairro, cidade, uf, cep)):
        return None
    return PacienteEndereco(
        paciente_id=paciente_id,
        tipo=tipo,
        logradouro=logradouro,
        bairro=bairro,
        cidade=cidade,
        uf=(uf or "")[:2] or None,
        cep=cep,
    )


def migrar(sessao: Session, extrato: Extrato, clinica_id: int) -> ResultadoPacientes:
    resultado = ResultadoPacientes()

    convenios = {
        c.codigo: c.id
        for c in sessao.scalars(select(Convenio).where(Convenio.clinica_id == clinica_id))
    }
    existentes = {
        p.codigo_legado: p
        for p in sessao.scalars(select(Paciente).where(Paciente.clinica_id == clinica_id))
    }
    nomes_repetidos = _duplicados_por_nome(extrato)

    for linha in extrato.linhas("ARQCLIEN", ordem="CODICLIE"):
        codigo = limpar(linha["CODICLIE"])
        if codigo in existentes:
            resultado.pacientes += 1
            continue

        motivos: list[str] = []
        nascimento, motivo_nasc = data_legada(linha["NASCIDO"])
        if motivo_nasc:
            motivos.append(motivo_nasc if motivo_nasc == "data_ilegivel" else "data_suspeita")
        ultimo, motivo_ultimo = data_legada(linha["DTSERV"])
        if motivo_ultimo == "data_suspeita" and "data_suspeita" not in motivos:
            motivos.append("data_suspeita")
        cadastrado, _ = data_legada(linha["DAT_CAD"])

        nome = limpar(linha["NOME"]) or f"(sem nome) {codigo}"
        if nome.upper() in nomes_repetidos:
            motivos.append("possivel_duplicata")

        cod_conv = (limpar(linha["CODCONV"]) or "").zfill(3)

        paciente = Paciente(
            clinica_id=clinica_id,
            codigo_legado=codigo,
            nome=nome,
            nascimento=nascimento,
            cpf=limpar(linha["CPF"]),
            ci=limpar(linha["CI"]),
            email=limpar(linha["EMAIL"]),
            profissao=limpar(linha["PROFISSAO"]),
            estado_civil=limpar(linha["ESTADOCIV"]),
            indicacao=limpar(linha["INDICACAO"]),
            pai=limpar(linha["PAI"]),
            mae=limpar(linha["MAE"]),
            convenio_id=convenios.get(cod_conv),
            cadastrado_em=cadastrado,
            ultimo_atendimento=ultimo,
        )
        sessao.add(paciente)
        sessao.flush()
        existentes[codigo] = paciente
        resultado.pacientes += 1

        bruto_residencial = linha["TELEFONE"]
        bruto_comercial = linha["TELECOM"]
        primeiro = True
        for bruto in (bruto_residencial, bruto_comercial):
            for numero in separar(bruto):
                if parecer_incompleto(numero) and "telefone_incompleto" not in motivos:
                    motivos.append("telefone_incompleto")
                sessao.add(
                    PacienteTelefone(
                        paciente_id=paciente.id,
                        numero=numero,
                        numero_original=limpar(bruto),
                        principal=primeiro,
                    )
                )
                resultado.telefones += 1
                primeiro = False

        for tipo, campos in (
            ("RESIDENCIAL", ("ENDERECO", "BAIRRO", "CIDADE", "UF", "CEP")),
            ("COMERCIAL", ("ENDCOM", "BAICOM", "CIDCOM", "UFCOM", "CEPCOM")),
        ):
            endereco = _endereco(paciente.id, tipo, linha, campos)
            if endereco is not None:
                sessao.add(endereco)
                resultado.enderecos += 1

        if motivos:
            paciente.revisar_motivo = motivos
            resultado.marcados += 1

    sessao.flush()
    return resultado
