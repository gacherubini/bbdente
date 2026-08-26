"""Prontuario do paciente em PDF.

Atende o direito de acesso da LGPD e serve para encaminhamento. Usa fpdf2, que e
Python puro — sem dependencia de sistema para instalar no Windows nem no container.
"""

from datetime import date

from fpdf import FPDF
from sqlalchemy.orm import Session

from app.clinico.service import anamnese, historico
from app.pacientes.service import obter as obter_paciente

ROXO = (91, 33, 182)
CINZA = (100, 116, 139)


class _Folha(FPDF):
    def __init__(self, clinica_nome: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.clinica_nome = clinica_nome
        self.set_auto_page_break(auto=True, margin=18)

    def header(self) -> None:
        self.set_font("helvetica", "B", 15)
        self.set_text_color(*ROXO)
        self.cell(0, 8, "BDDente", new_x="LMARGIN", new_y="NEXT")
        self.set_font("helvetica", "", 9)
        self.set_text_color(*CINZA)
        self.cell(0, 5, self.clinica_nome, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_draw_color(196, 181, 253)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("helvetica", "", 8)
        self.set_text_color(*CINZA)
        self.cell(
            0, 5,
            f"Emitido em {date.today().strftime('%d/%m/%Y')} - pagina {self.page_no()}",
            align="C",
        )

    def titulo(self, texto: str) -> None:
        self.ln(3)
        self.set_font("helvetica", "B", 11)
        self.set_text_color(15, 23, 42)
        self.cell(0, 7, texto, new_x="LMARGIN", new_y="NEXT")

    def linha(self, rotulo: str, valor: str) -> None:
        self.set_font("helvetica", "", 9.5)
        self.set_text_color(*CINZA)
        self.cell(38, 6, rotulo)
        self.set_text_color(15, 23, 42)
        self.multi_cell(0, 6, valor or "-", new_x="LMARGIN", new_y="NEXT")


def _texto(valor: object) -> str:
    """fpdf2 com as fontes embutidas so escreve latin-1. Trocamos o que nao couber
    em vez de deixar a geracao estourar num nome com acento incomum."""
    bruto = "" if valor is None else str(valor)
    return bruto.encode("latin-1", "replace").decode("latin-1")


def gerar(
    sessao: Session, *, clinica_id: int, paciente_id: int, clinica_nome: str
) -> bytes:
    paciente = obter_paciente(
        sessao, clinica_id=clinica_id, paciente_id=paciente_id
    )
    if paciente is None:
        raise LookupError("paciente nao encontrado nesta clinica")

    folha = _Folha(_texto(clinica_nome))
    folha.add_page()

    folha.set_font("helvetica", "B", 14)
    folha.set_text_color(15, 23, 42)
    folha.cell(0, 9, _texto(paciente.nome), new_x="LMARGIN", new_y="NEXT")

    folha.titulo("Dados do paciente")
    folha.linha("Codigo", _texto(paciente.codigo_legado))
    folha.linha(
        "Nascimento",
        paciente.nascimento.strftime("%d/%m/%Y") if paciente.nascimento else "-",
    )
    folha.linha("CPF", _texto(paciente.cpf))
    folha.linha(
        "Telefones",
        ", ".join(_texto(t.numero) for t in paciente.telefones) or "-",
    )
    if paciente.revisar_motivo:
        folha.linha("A conferir", _texto(", ".join(paciente.revisar_motivo)))

    folha.titulo("Historico de tratamentos")
    itens = historico(sessao, clinica_id=clinica_id, paciente_id=paciente_id)
    if not itens:
        folha.set_font("helvetica", "", 9.5)
        folha.set_text_color(*CINZA)
        folha.cell(0, 6, "Nenhum lancamento registrado.", new_x="LMARGIN", new_y="NEXT")
    else:
        folha.set_font("helvetica", "B", 8.5)
        folha.set_text_color(*CINZA)
        for largura, cabecalho in (
            (24, "Data"), (18, "Dente"), (86, "Tratamento"),
            (26, "Situacao"), (24, "Valor"),
        ):
            folha.cell(largura, 6, cabecalho)
        folha.ln(6)
        folha.set_font("helvetica", "", 9)
        folha.set_text_color(15, 23, 42)
        for item in itens:
            folha.cell(24, 5.5, item["data"].strftime("%d/%m/%Y") if item["data"] else "-")
            folha.cell(18, 5.5, str(item["dente"]) if item["dente"] else "boca")
            folha.cell(86, 5.5, _texto(item["procedimento"])[:52])
            folha.cell(
                26, 5.5,
                "Realizado" if item["status"] == "REALIZADO" else "Planejado",
            )
            folha.cell(24, 5.5, f"R$ {item['valor']}")
            folha.ln(5.5)

    respostas = [
        item
        for item in anamnese(sessao, clinica_id=clinica_id, paciente_id=paciente_id)
        if item["resposta"]
    ]
    if respostas:
        folha.titulo("Anamnese")
        folha.set_font("helvetica", "", 9)
        for item in respostas:
            folha.set_text_color(*CINZA)
            folha.multi_cell(0, 5, _texto(item["texto"]), new_x="LMARGIN", new_y="NEXT")
            folha.set_text_color(15, 23, 42)
            folha.multi_cell(
                0, 5, "   " + _texto(item["resposta"]), new_x="LMARGIN", new_y="NEXT"
            )

    return bytes(folha.output())
