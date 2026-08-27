from datetime import date

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.auth.models import Usuario
from app.auth.sessao import usuario_atual

# Convenio pertence ao catalogo: pedimos a lista pela service dele, nunca pelo model.
from app.catalogo.service import convenios
from app.pacientes.service import (
    Endereco,
    Filtro,
    Ordem,
    atualizar,
    buscar,
    contagens,
    criar,
    obter,
    semelhantes,
)
from app.pacientes.telefone import formatar
from app.shared.db import obter_sessao
from app.templates import templates

# Os campos alem do essencial. Ficam numa lista so para que a tela de cadastro e a
# de edicao nunca divirjam sobre o que a ficha tem.
CAMPOS_DA_FICHA = (
    "cpf", "indicacao", "observacao",
    "cep", "logradouro", "bairro", "cidade", "uf",
)

UFS = (
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT",
    "PA", "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP",
    "TO",
)


def _ficha(**campos: str) -> dict[str, str]:
    """O que veio nos campos da ficha, sempre com todas as chaves — o template le
    todas, e chave faltando viraria string vazia silenciosa no Jinja."""
    return {nome: (campos.get(nome) or "") for nome in CAMPOS_DA_FICHA}


def _endereco_de(dados: dict[str, str]) -> Endereco:
    return Endereco(
        logradouro=dados["logradouro"],
        bairro=dados["bairro"],
        cidade=dados["cidade"],
        uf=dados["uf"],
        cep=dados["cep"],
    )


router = APIRouter()


@router.get("/pacientes", response_class=HTMLResponse)
def listar(
    request: Request,
    q: str = Query(""),
    filtro: str = Query(Filtro.ATIVOS.value),
    ordem: str = Query(Ordem.ATENDIMENTO.value),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    try:
        escolhido = Filtro(filtro)
    except ValueError:
        escolhido = Filtro.ATIVOS  # filtro inventado na URL nao derruba a tela
    try:
        ordenacao = Ordem(ordem)
    except ValueError:
        ordenacao = Ordem.ATENDIMENTO

    return templates.TemplateResponse(
        request,
        "pacientes.html",
        {
            "aba": "pacientes",
            "termo": q,
            "filtro": escolhido,
            "filtros": list(Filtro),
            "ordem": ordenacao,
            "ordens": list(Ordem),
            "linhas": buscar(
                sessao,
                clinica_id=usuario.clinica_id,
                termo=q,
                filtro=escolhido,
                ordem=ordenacao,
            ),
            "numeros": contagens(sessao, clinica_id=usuario.clinica_id),
        },
    )


def _formulario(
    request: Request,
    sessao: Session,
    clinica_id: int,
    dados: dict[str, str],
    *,
    erro: str | None = None,
    parecidos: list | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "paciente_novo.html",
        {
            "aba": "pacientes",
            "dados": dados,
            "erro": erro,
            "parecidos": parecidos or [],
            "convenios": convenios(sessao, clinica_id=clinica_id),
            "ufs": UFS,
        },
        status_code=200,
    )


@router.get("/pacientes/novo", response_class=HTMLResponse)
def novo(
    request: Request,
    nome: str = Query(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    """O nome ja vem preenchido com o termo que a busca nao achou."""
    dados = {"nome": nome, "telefone": "", "nascimento": "", "convenio_id": ""}
    dados.update(_ficha())
    return _formulario(request, sessao, usuario.clinica_id, dados)


@router.post("/pacientes/novo")
def cadastrar(
    request: Request,
    nome: str = Form(""),
    telefone: str = Form(""),
    nascimento: str = Form(""),
    convenio_id: str = Form(""),
    confirmar: str = Form(""),
    cpf: str = Form(""),
    indicacao: str = Form(""),
    observacao: str = Form(""),
    cep: str = Form(""),
    logradouro: str = Form(""),
    bairro: str = Form(""),
    cidade: str = Form(""),
    uf: str = Form(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    dados = {
        "nome": nome,
        "telefone": telefone,
        "nascimento": nascimento,
        "convenio_id": convenio_id,
        **_ficha(
            cpf=cpf, indicacao=indicacao, observacao=observacao, cep=cep,
            logradouro=logradouro, bairro=bairro, cidade=cidade, uf=uf,
        ),
    }
    def formulario(**kw) -> HTMLResponse:
        return _formulario(request, sessao, usuario.clinica_id, dados, **kw)

    if not nome.strip():
        return formulario(erro="Digite o nome do paciente.")

    try:
        nasceu = date.fromisoformat(nascimento) if nascimento.strip() else None
    except ValueError:
        return formulario(erro="Data de nascimento inválida.")

    # Duplicata em base de 30 anos e o erro caro. Avisamos ANTES de gravar; quem
    # cadastra decide, porque so ela sabe se sao duas pessoas ou a mesma.
    if confirmar != "1":
        parecidos = semelhantes(sessao, clinica_id=usuario.clinica_id, nome=nome)
        if parecidos:
            return formulario(parecidos=parecidos)

    try:
        paciente = criar(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            nome=nome,
            telefone=telefone.strip() or None,
            nascimento=nasceu,
            convenio_id=int(convenio_id) if convenio_id.strip() else None,
            cpf=cpf,
            indicacao=indicacao,
            observacao=observacao,
            endereco=_endereco_de(dados),
        )
    except ValueError as erro:
        sessao.rollback()
        return formulario(erro=str(erro))

    sessao.commit()
    # Quem cadastra esta com a pessoa na frente: o proximo passo e o odontograma.
    return RedirectResponse(f"/odontograma/{paciente.id}", status_code=303)


def _obter(sessao: Session, clinica_id: int, paciente_id: int):
    paciente = obter(sessao, clinica_id=clinica_id, paciente_id=paciente_id)
    if paciente is None:
        raise HTTPException(status_code=404, detail="paciente nao encontrado")
    return paciente


def _tela_de_edicao(
    request: Request,
    sessao: Session,
    clinica_id: int,
    paciente,
    dados: dict[str, str],
    erro: str | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "paciente_editar.html",
        {
            "aba": "pacientes",
            "paciente": paciente,
            "dados": dados,
            "erro": erro,
            "convenios": convenios(sessao, clinica_id=clinica_id),
            "ufs": UFS,
        },
        status_code=200,
    )


def _dados_de(paciente) -> dict[str, str]:
    return {
        "nome": paciente.nome,
        # Os numeros vao separados por barra, que e como a migracao os leu do
        # Dentalis e como o separador volta a le-los.
        "telefone": " / ".join(formatar(t.numero) for t in paciente.telefones),
        "nascimento": paciente.nascimento.isoformat() if paciente.nascimento else "",
        "convenio_id": str(paciente.convenio_id or ""),
        # A tela edita so o residencial; o comercial migrado continua no banco.
        **_ficha(
            cpf=paciente.cpf,
            indicacao=paciente.indicacao,
            observacao=paciente.observacao,
            **_residencial(paciente),
        ),
    }


def _residencial(paciente) -> dict[str, str]:
    casa = next(
        (e for e in paciente.enderecos if e.tipo == "RESIDENCIAL"), None
    )
    if casa is None:
        return {}
    return {
        "cep": casa.cep or "",
        "logradouro": casa.logradouro or "",
        "bairro": casa.bairro or "",
        "cidade": casa.cidade or "",
        "uf": casa.uf or "",
    }


@router.get("/pacientes/{paciente_id}/editar", response_class=HTMLResponse)
def editar(
    request: Request,
    paciente_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    paciente = _obter(sessao, usuario.clinica_id, paciente_id)
    return _tela_de_edicao(
        request, sessao, usuario.clinica_id, paciente, _dados_de(paciente)
    )


@router.post("/pacientes/{paciente_id}/editar")
def salvar_edicao(
    request: Request,
    paciente_id: int,
    nome: str = Form(""),
    telefone: str = Form(""),
    nascimento: str = Form(""),
    convenio_id: str = Form(""),
    cpf: str = Form(""),
    indicacao: str = Form(""),
    observacao: str = Form(""),
    cep: str = Form(""),
    logradouro: str = Form(""),
    bairro: str = Form(""),
    cidade: str = Form(""),
    uf: str = Form(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    paciente = _obter(sessao, usuario.clinica_id, paciente_id)
    dados = {
        "nome": nome,
        "telefone": telefone,
        "nascimento": nascimento,
        "convenio_id": convenio_id,
        **_ficha(
            cpf=cpf, indicacao=indicacao, observacao=observacao, cep=cep,
            logradouro=logradouro, bairro=bairro, cidade=cidade, uf=uf,
        ),
    }

    def formulario(erro: str) -> HTMLResponse:
        return _tela_de_edicao(
            request, sessao, usuario.clinica_id, paciente, dados, erro=erro
        )

    if not nome.strip():
        return formulario("Digite o nome do paciente.")
    try:
        nasceu = date.fromisoformat(nascimento) if nascimento.strip() else None
    except ValueError:
        return formulario("Data de nascimento inválida.")

    try:
        atualizar(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            paciente_id=paciente.id,
            nome=nome,
            telefone=telefone,
            nascimento=nasceu,
            convenio_id=int(convenio_id) if convenio_id.strip() else None,
            cpf=cpf,
            indicacao=indicacao,
            observacao=observacao,
            endereco=_endereco_de(dados),
        )
    except ValueError as erro:
        return formulario(str(erro))

    sessao.commit()
    return RedirectResponse(f"/odontograma/{paciente.id}", status_code=303)
