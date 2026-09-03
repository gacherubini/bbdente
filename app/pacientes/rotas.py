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
    definir_consentimento,
    excluir,
    obter,
    semelhantes,
    vinculos_de,
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

# As tres respostas possiveis. "nao_perguntado" desfaz uma resposta dada por
# engano e so aparece na ficha — na agenda o clique de passagem tem duas saidas,
# porque quem esta com a paciente na frente ou ouviu "pode" ou ouviu "nao".
RESPOSTAS_DE_WHATSAPP = {"sim": True, "nao": False, "nao_perguntado": None}




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
    aceita_whatsapp: str = Form(""),
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
        "aceita_whatsapp": aceita_whatsapp,
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
            # Campo em branco = nunca perguntamos. Nao e "nao"; e a ausencia de
            # pergunta, e ela nao recebe mensagem enquanto for isso.
            aceita_whatsapp=RESPOSTAS_DE_WHATSAPP.get(aceita_whatsapp),
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


def _destino_interno(bruto: str, padrao: str) -> str:
    """Endereco de volta que veio de formulario.

    Formulario e coisa que se edita. Aceitar endereco de fora aqui e
    redirecionamento aberto — o sistema mandando a dentista para um site que nao
    e dele, com a barra de endereco dizendo que partiu daqui.
    """
    if bruto.startswith("/") and not bruto.startswith("//"):
        return bruto
    return padrao


@router.post("/pacientes/{paciente_id}/whatsapp")
def responder_whatsapp(
    paciente_id: int,
    aceita: str = Form(""),
    voltar: str = Form(""),
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    """Registra a autorizacao de mandar lembrete, num clique.

    Existe para ser chamada do cartao da agenda, com a paciente ali marcando o
    retorno: a base de autorizacao so cresce se perguntar for barato. Mandar uma
    mensagem para todo mundo perguntando se pode mandar mensagem ja e a mensagem
    que nao podia mandar.
    """
    if aceita not in RESPOSTAS_DE_WHATSAPP:
        raise HTTPException(status_code=400, detail="resposta invalida")

    try:
        definir_consentimento(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            paciente_id=paciente_id,
            aceita=RESPOSTAS_DE_WHATSAPP[aceita],
        )
    except LookupError as erro:
        raise HTTPException(status_code=404, detail="paciente nao encontrado") from erro

    sessao.commit()
    return RedirectResponse(
        _destino_interno(voltar, f"/pacientes/{paciente_id}/editar"), status_code=303
    )


def _quantos(quantidade: int, singular: str, plural: str) -> str | None:
    """'1 tratamento', '12 tratamentos', nada quando e zero."""
    if not quantidade:
        return None
    return f"{quantidade} {singular if quantidade == 1 else plural}"


def _avisos_de(vinculos) -> list[str]:
    """O que a pessoa precisa saber ANTES de clicar, em portugues.

    A ordem nao e alfabetica nem por tamanho: e a do peso da decisao. Prontuario
    primeiro, porque tratamento e o que a clinica existe para guardar; dinheiro
    por ultimo, porque parcela em aberto continua cobravel depois — a lista de
    cobranca le o nome por `nomes_de`, que nao filtra excluido.
    """
    frases = (
        _quantos(vinculos.tratamentos, "tratamento", "tratamentos"),
        _quantos(vinculos.agendamentos, "horário marcado", "horários marcados"),
        _quantos(
            vinculos.parcelas_em_aberto, "parcela em aberto", "parcelas em aberto"
        ),
    )
    return [frase for frase in frases if frase]


@router.get("/pacientes/{paciente_id}/excluir", response_class=HTMLResponse)
def confirmar_exclusao(
    request: Request,
    paciente_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    """A tela do aviso. Nao exclui nada — GET nunca escreve.

    Existe como tela, e nao como `confirm()` do navegador, porque a frase que
    importa tem numeros que so o banco sabe: quem esta prestes a excluir um
    cadastro com 12 tratamentos precisa ver o 12.
    """
    paciente = _obter(sessao, usuario.clinica_id, paciente_id)
    vinculos = vinculos_de(
        sessao, clinica_id=usuario.clinica_id, paciente_id=paciente.id
    )
    return templates.TemplateResponse(
        request,
        "paciente_excluir.html",
        {
            "aba": "pacientes",
            "paciente": paciente,
            "vinculos": vinculos,
            "avisos": _avisos_de(vinculos),
        },
    )


@router.post("/pacientes/{paciente_id}/excluir")
def excluir_paciente(
    paciente_id: int,
    usuario: Usuario = Depends(usuario_atual),
    sessao: Session = Depends(obter_sessao),
):
    """Exclui o cadastro e derruba os horarios que ele ainda ocupa.

    As duas escritas moram aqui, e nao em `pacientes.service`, porque
    `agenda.service` importa `pacientes.service`: chamar a volta de dentro da
    service seria ciclo de import de verdade. Mesma razao — e mesmo lugar — do
    `vincular_paciente`, que `clinico/api.py` chama e `clinico/service.py` nao.

    A ordem importa. O cadastro sai primeiro: se a agenda falhar no meio, o
    `rollback` desfaz as duas, e ninguem fica com cadastro excluido e horario
    de pe. Um commit so.
    """
    # Import local: `agenda.service` importa `pacientes.service`, e no topo
    # deste arquivo nao ha ciclo — mas mante-lo aqui deixa a direcao obvia para
    # quem ler a rota.
    from app.agenda import service as agenda

    paciente = _obter(sessao, usuario.clinica_id, paciente_id)

    excluir(
        sessao,
        clinica_id=usuario.clinica_id,
        usuario_id=usuario.id,
        paciente_id=paciente.id,
    )

    # So daqui para frente. O passado da agenda e historico — apagar nao desfaz
    # a consulta que aconteceu, so esconde que ela aconteceu.
    for agendamento in agenda.futuros_do_paciente(
        sessao,
        clinica_id=usuario.clinica_id,
        paciente_id=paciente.id,
        desde=date.today(),
    ):
        agenda.excluir(
            sessao,
            clinica_id=usuario.clinica_id,
            usuario_id=usuario.id,
            agendamento_id=agendamento.id,
        )

    sessao.commit()
    return RedirectResponse("/pacientes", status_code=303)
