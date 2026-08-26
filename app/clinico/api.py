from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.clinico.service import (
    EscopoInvalido,
    ItemAtendimento,
    estado_de_previa,
    estado_do_odontograma,
    excluir_lancamento,
    lancar,
    lancar_atendimento,
    validar_atendimento,
)

# Fronteira de modulo: paciente so pela service dele, nunca pelo model.
from app.pacientes.service import criar as criar_paciente
from app.pacientes.service import obter as obter_paciente
from app.pacientes.service import semelhantes
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento

router = APIRouter(prefix="/api")


def _para_decimal(bruto: str | None) -> Decimal | None:
    if not bruto:
        return None
    try:
        return Decimal(bruto)
    except InvalidOperation as erro:
        raise HTTPException(status_code=422, detail="valor invalido") from erro


def _para_data(bruto: str | None) -> date | None:
    if not bruto:
        return None
    try:
        return date.fromisoformat(bruto)
    except ValueError as erro:
        raise HTTPException(status_code=422, detail="data invalida") from erro


class NovoLancamento(BaseModel):
    paciente_id: int
    procedimento_id: int
    escopo: Escopo
    dente: int | None = None
    regioes: list[Regiao] = Field(default_factory=list)
    status: StatusLancamento
    data: str | None = None
    valor: str | None = None
    observacao: str | None = None
    numero_odontograma: int = 1


class ItemPendente(BaseModel):
    """Um tratamento do atendimento que ainda nao tem dono."""

    procedimento_id: int
    escopo: Escopo
    dente: int | None = None
    regioes: list[Regiao] = Field(default_factory=list)
    status: StatusLancamento
    data: str | None = None
    valor: str | None = None
    observacao: str | None = None

    def para_dominio(self) -> ItemAtendimento:
        return ItemAtendimento(
            procedimento_id=self.procedimento_id,
            escopo=self.escopo,
            status=self.status,
            dente=self.dente,
            regioes=tuple(self.regioes),
            data=_para_data(self.data),
            valor=_para_decimal(self.valor),
            observacao=self.observacao,
        )


class Previa(BaseModel):
    itens: list[ItemPendente] = Field(default_factory=list)


class PacienteNovo(BaseModel):
    nome: str = ""
    telefone: str | None = None
    nascimento: str | None = None
    convenio_id: int | None = None


class Atendimento(BaseModel):
    """Ou aponta um paciente que ja existe, ou traz o cadastro para criar na hora."""

    paciente_id: int | None = None
    novo: PacienteNovo | None = None
    confirmar: bool = False
    itens: list[ItemPendente] = Field(default_factory=list)
    numero_odontograma: int = 1


@router.get("/odontograma/{paciente_id}")
def obter_estado(
    paciente_id: int,
    numero: int = 1,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    try:
        return estado_do_odontograma(
            sessao, clinica_id=usuario.clinica_id, paciente_id=paciente_id, numero=numero
        )
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro


@router.post("/odontograma/previa")
def previa(
    corpo: Previa,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    """Devolve o desenho pintado de um atendimento que ainda NAO foi gravado.

    Nao escreve nada. Existe para o JavaScript nao precisar reimplementar a regra
    de qual cor vence quando dois tratamentos caem no mesmo lugar.
    """
    try:
        return estado_de_previa(
            sessao,
            clinica_id=usuario.clinica_id,
            itens=[item.para_dominio() for item in corpo.itens],
        )
    except EscopoInvalido as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro


@router.post("/atendimento", status_code=201)
def concluir_atendimento(
    corpo: Atendimento,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    """Fecha o atendimento da tela em branco: agora se sabe de quem e, grava tudo.

    Se o cadastro e novo e ja existe gente parecida, responde 200 com a lista de
    parecidos e NAO grava — quem atende decide se e a mesma pessoa.
    """
    if corpo.paciente_id is None and corpo.novo is None:
        raise HTTPException(status_code=422, detail="diga de quem e o atendimento")

    itens = [item.para_dominio() for item in corpo.itens]
    # Confere o atendimento inteiro ANTES de tocar no banco: um item errado nao
    # pode deixar para tras um paciente que so foi criado para recebe-lo.
    try:
        validar_atendimento(sessao, clinica_id=usuario.clinica_id, itens=itens)
    except EscopoInvalido as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro

    if corpo.paciente_id is not None:
        paciente = obter_paciente(
            sessao, clinica_id=usuario.clinica_id, paciente_id=corpo.paciente_id
        )
        if paciente is None:
            raise HTTPException(status_code=404, detail="paciente nao encontrado")
        paciente_id = paciente.id
    else:
        nome = (corpo.novo.nome or "").strip()
        if not nome:
            raise HTTPException(
                status_code=422, detail="o nome do paciente e obrigatorio"
            )
        if not corpo.confirmar:
            parecidos = semelhantes(
                sessao, clinica_id=usuario.clinica_id, nome=nome
            )
            if parecidos:
                return JSONResponse(
                    status_code=200,
                    content={
                        "parecidos": [
                            {
                                "id": linha.id,
                                "nome": linha.nome,
                                "codigo_legado": linha.codigo_legado,
                                "ultimo_atendimento": (
                                    linha.ultimo_atendimento.isoformat()
                                    if linha.ultimo_atendimento
                                    else None
                                ),
                            }
                            for linha in parecidos
                        ]
                    },
                )
        try:
            criado = criar_paciente(
                sessao,
                clinica_id=usuario.clinica_id,
                usuario_id=usuario.id,
                nome=nome,
                telefone=corpo.novo.telefone,
                nascimento=_para_data(corpo.novo.nascimento),
                convenio_id=corpo.novo.convenio_id,
            )
        except ValueError as erro:
            sessao.rollback()
            raise HTTPException(status_code=422, detail=str(erro)) from erro
        paciente_id = criado.id

    try:
        lancamentos = lancar_atendimento(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            paciente_id=paciente_id,
            itens=itens,
            numero_odontograma=corpo.numero_odontograma,
        )
    except EscopoInvalido as erro:
        sessao.rollback()
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    except LookupError as erro:
        sessao.rollback()
        raise HTTPException(status_code=404, detail=str(erro)) from erro

    sessao.commit()
    return {"paciente_id": paciente_id, "lancamentos": len(lancamentos)}


@router.post("/lancamento", status_code=201)
def criar_lancamento(
    corpo: NovoLancamento,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    try:
        lancamento = lancar(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            paciente_id=corpo.paciente_id,
            procedimento_id=corpo.procedimento_id,
            escopo=corpo.escopo,
            dente=corpo.dente,
            regioes=corpo.regioes,
            status=corpo.status,
            data=_para_data(corpo.data),
            valor=_para_decimal(corpo.valor),
            observacao=corpo.observacao,
            numero_odontograma=corpo.numero_odontograma,
        )
    except EscopoInvalido as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    except LookupError as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from erro

    sessao.commit()
    return {
        "lancamento_id": lancamento.id,
        "estado": estado_do_odontograma(
            sessao,
            clinica_id=usuario.clinica_id,
            paciente_id=corpo.paciente_id,
            numero=corpo.numero_odontograma,
        ),
    }


@router.delete("/lancamento/{lancamento_id}")
def apagar_lancamento(
    lancamento_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    if not excluir_lancamento(
        sessao,
        clinica_id=usuario.clinica_id,
        usuario_id=usuario.id,
        lancamento_id=lancamento_id,
    ):
        raise HTTPException(status_code=404, detail="lancamento nao encontrado")
    sessao.commit()
    return {"ok": True}
