"""Migra as 28.244 parcelas do ARQFAT — o livro-caixa de 30 anos do consultorio.

O ARQFAT nao tem chave primaria propria. A identidade de uma parcela aqui e
(CODICLIE, PARCELA, DTVENCTO, ordem-na-leitura), gravada em `codigo_legado` — e o
que torna esta migracao idempotente.

Duas leituras que valem registrar, porque decidem o que os relatorios significam:

- **`VALORPAG` e o dinheiro que entrou.** A soma dele (R$ 2.378.315,73) bate com a
  soma dos lancamentos realizados ja migrados (R$ 2.374.762,13) — duas fontes
  independentes contando a mesma coisa, com R$ 3.553,60 de diferenca em 30 anos.
- **`PARCIAL = 'S'` explica o resto.** 7.849 parcelas tem data de pagamento e
  ainda assim sobrou saldo: foram pagas pela metade. Por isso o que esta em
  aberto de verdade e `cobrado - pago` (R$ 3.430.481,53), e nao a soma das
  parcelas sem data de pagamento (R$ 1.299.587,61).
"""

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.financeiro.models import Parcela
from app.pacientes.models import Paciente
from migracao.extrato import Extrato
from migracao.texto import data_legada, limpar

# 28.234 das 28.244 linhas tem CODTPAG '00', que no ARQTPAG e a descricao vazia.
# Forma de pagamento praticamente nao existe no historico: entra nula em vez de
# virar a string '00', que fingiria informacao.
CODIGO_SEM_FORMA = "00"


def _degraus_de_carne(extrato: Extrato) -> set[int]:
    """As linhas que sao degrau de um carne, pela ordem de leitura.

    O Dentalis nao tinha tabela de carne: quando o paciente pagava uma parcela,
    ele REGRAVAVA o saldo restante numa linha nova, com o mesmo vencimento. Sete
    linhas com valor caindo 1.200, 1.050, 900, 750, 600, 450, 300 e R$ 150 pagos
    em cada nao sao sete dividas de R$ 5.250 — sao uma divida de R$ 1.200 paga em
    sete vezes, com R$ 150 ainda em aberto.

    Somar todas inflaria o que ha para receber em R$ 1.392.888,31 (41%). Entao
    marcamos as linhas ja superadas: elas continuam no banco, com o valor como
    veio, mas ficam de fora da conta da divida. Os pagamentos delas continuam
    contando — cada um foi dinheiro que entrou de verdade.

    A regra e deliberadamente estreita, e so pega grupo que nao deixa duvida:
    mesmo paciente, mesmo vencimento, valores estritamente decrescentes, e cada
    degrau igual ao valor pago naquela linha. Sao 3.014 grupos, 8.177 linhas.
    """
    grupos: dict[tuple, list[tuple[int, Decimal, Decimal]]] = {}
    for ordem, linha in enumerate(extrato.linhas("ARQFAT")):
        chave = (limpar(linha["CODICLIE"]), limpar(linha["DTVENCTO"]))
        grupos.setdefault(chave, []).append(
            (ordem, _valor(linha["ORIGINAL"]), _valor(linha["VALORPAG"]))
        )

    superadas: set[int] = set()
    for linhas in grupos.values():
        if len(linhas) < 2:
            continue
        emordem = sorted(linhas, key=lambda item: item[1], reverse=True)
        valores = [valor for _, valor, _ in emordem]
        if len(set(valores)) != len(valores):
            continue  # empate: nao da para dizer qual veio antes
        pagos = [pago for _, _, pago in emordem]
        degraus = [valores[i] - valores[i + 1] for i in range(len(valores) - 1)]
        if degraus != pagos[:-1]:
            continue
        # A ultima (menor valor) e a divida que sobrou; as anteriores ja foram
        # substituidas por ela.
        superadas.update(ordem for ordem, _, _ in emordem[:-1])
    return superadas


@dataclass
class ResultadoFinanceiro:
    parcelas: int = 0
    marcadas: int = 0
    substituidas: int = 0
    ja_existiam: int = 0
    soma_cobrada: Decimal = field(default_factory=lambda: Decimal("0"))
    soma_paga: Decimal = field(default_factory=lambda: Decimal("0"))

    def __str__(self) -> str:
        return (
            f"{self.parcelas} parcelas "
            f"(cobrado R$ {self.soma_cobrada}, pago R$ {self.soma_paga}), "
            f"{self.marcadas} marcadas para revisar, "
            f"{self.substituidas} substituidas por outra do mesmo carne, "
            f"{self.ja_existiam} ja estavam no banco"
        )


def _valor(bruto) -> Decimal:
    try:
        return Decimal(str(bruto or 0)).quantize(Decimal("0.01"))
    except (TypeError, ArithmeticError):
        return Decimal("0.00")


def _formas_de_pagamento(extrato: Extrato) -> dict[str, str]:
    """ARQTPAG: 00 vazio, 01 Dinheiro, 02 Cheque, 03 Cheque Pre, 04 Cartao, 05 Boleto."""
    formas: dict[str, str] = {}
    for linha in extrato.linhas("ARQTPAG"):
        codigo = (limpar(linha["CODIGO"]) or "").strip()
        descricao = limpar(linha["DESCRICAO"])
        if codigo and descricao:
            formas[codigo] = descricao
    return formas


def migrar(sessao: Session, extrato: Extrato, clinica_id: int) -> ResultadoFinanceiro:
    resultado = ResultadoFinanceiro()

    pacientes = {
        p.codigo_legado: p.id
        for p in sessao.scalars(select(Paciente).where(Paciente.clinica_id == clinica_id))
    }
    formas = _formas_de_pagamento(extrato)
    degraus = _degraus_de_carne(extrato)
    ja_migradas = {
        codigo
        for (codigo,) in sessao.query(Parcela.codigo_legado).filter(
            Parcela.clinica_id == clinica_id, Parcela.codigo_legado.isnot(None)
        )
    }

    for ordem, linha in enumerate(extrato.linhas("ARQFAT")):
        codigo_paciente = limpar(linha["CODICLIE"])
        paciente_id = pacientes.get(codigo_paciente)
        if paciente_id is None:
            # O extrato provou ter zero referencias orfas no ARQFAT. Uma aqui
            # seria bug de codigo, nao dado ruim — e migrar torto um livro-caixa
            # de 30 anos e pior do que nao migrar.
            raise ValueError(f"parcela aponta para paciente inexistente: {codigo_paciente!r}")

        numero = (limpar(linha["PARCELA"]) or "")[:10]
        # Truncado JA AQUI, e nao so na hora de gravar: a chave que procura no
        # banco tem de ser identica a que foi guardada, senao a segunda rodada
        # nao reconhece nada e duplica tudo.
        codigo_legado = f"{codigo_paciente}|{numero}|{limpar(linha['DTVENCTO'])}#{ordem}"[:40]
        if codigo_legado in ja_migradas:
            resultado.parcelas += 1
            resultado.ja_existiam += 1
            continue

        vencimento, motivo_vencimento = data_legada(linha["DTVENCTO"])
        pago_em, motivo_pagamento = data_legada(linha["DTPAGTO"])
        motivos = [m for m in (motivo_vencimento, motivo_pagamento) if m]

        if vencimento is None:
            # `vencimento` e obrigatorio na tabela. Nenhuma linha do extrato cai
            # aqui hoje; se cair um dia, a data do pagamento serve de ancora
            # antes de inventar uma.
            vencimento = pago_em
            if vencimento is None:
                raise ValueError(f"parcela sem data nenhuma: {codigo_legado}")
            motivos.append("vencimento_ausente")

        codigo_forma = (limpar(linha["CODTPAG"]) or "").strip()
        forma = (
            formas.get(codigo_forma) if codigo_forma != CODIGO_SEM_FORMA else None
        )

        cobrado = _valor(linha["ORIGINAL"])
        pago = _valor(linha["VALORPAG"])

        sessao.add(
            Parcela(
                clinica_id=clinica_id,
                paciente_id=paciente_id,
                numero=numero,
                vencimento=vencimento,
                valor_cobrado=cobrado,
                valor_corrigido=_valor(linha["VALORREC"]),
                pago_em=pago_em,
                valor_pago=pago,
                juros=_valor(linha["JUROS"]),
                multa=_valor(linha["MULTA"]),
                desconto=_valor(linha["DESCONTO"]),
                forma_pagamento=forma,
                observacao=limpar(linha["OBSERV"]),
                substituida=ordem in degraus,
                codigo_legado=codigo_legado,
                revisar_motivo=motivos,
            )
        )
        resultado.parcelas += 1
        if ordem in degraus:
            resultado.substituidas += 1
        resultado.soma_cobrada += cobrado
        resultado.soma_paga += pago
        if motivos:
            resultado.marcadas += 1

    sessao.flush()
    return resultado
