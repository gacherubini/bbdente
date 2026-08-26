from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.clinico.service import (
    EscopoInvalido,
    estado_do_odontograma,
    excluir_lancamento,
    lancar,
)
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento

router = APIRouter(prefix="/api")


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


@router.post("/lancamento", status_code=201)
def criar_lancamento(
    corpo: NovoLancamento,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    from datetime import date as _date

    try:
        valor = Decimal(corpo.valor) if corpo.valor else None
    except InvalidOperation as erro:
        raise HTTPException(status_code=422, detail="valor invalido") from erro
    try:
        quando = _date.fromisoformat(corpo.data) if corpo.data else None
    except ValueError as erro:
        raise HTTPException(status_code=422, detail="data invalida") from erro

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
            data=quando,
            valor=valor,
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
