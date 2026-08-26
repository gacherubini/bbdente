"""Busca de paciente em JSON, para a janela que fecha o atendimento.

E a mesma `buscar()` da lista — nome, telefone ou codigo do Dentalis. Duas buscas
diferentes significariam achar o paciente numa tela e nao achar na outra.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual
from app.pacientes.service import Filtro, buscar
from app.shared.db import obter_sessao

router = APIRouter(prefix="/api")

# A janela e um atalho, nao a lista: 20 nomes cabem sem rolar.
LIMITE_DA_JANELA = 20


@router.get("/pacientes")
def procurar(
    q: str = Query(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    termo = q.strip()
    # Sem termo nao devolve nada: abrir a janela nao e motivo para carregar os
    # 5.561 cadastros.
    if not termo:
        return {"pacientes": []}

    linhas = buscar(
        sessao,
        clinica_id=usuario.clinica_id,
        termo=termo,
        filtro=Filtro.TODOS,
        limite=LIMITE_DA_JANELA,
    )
    return {
        "pacientes": [
            {
                "id": linha.id,
                "nome": linha.nome,
                "codigo_legado": linha.codigo_legado,
                "telefone": linha.telefone,
                "ultimo_atendimento": (
                    linha.ultimo_atendimento.isoformat()
                    if linha.ultimo_atendimento
                    else None
                ),
            }
            for linha in linhas
        ]
    }
