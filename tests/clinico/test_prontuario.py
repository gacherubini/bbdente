from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Procedimento
from app.clinico.prontuario import gerar
from app.clinico.service import lancar
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento


@pytest.fixture
def base(sessao):
    clinica = Clinica(nome="Consultorio Dra. Katia")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    paciente = Paciente(
        clinica_id=clinica.id, codigo_legado="6612/PT",
        nome="Amanda Ribeiro Nogueira", nascimento=date(1990, 3, 2),
    )
    sessao.add_all([categoria, paciente])
    sessao.flush()
    proc = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao Classe II",
        categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES, regioes_sugeridas=[],
    )
    sessao.add(proc)
    sessao.flush()
    lancar(
        sessao, clinica_id=clinica.id, usuario_id=usuario.id, paciente_id=paciente.id,
        procedimento_id=proc.id, escopo=Escopo.REGIOES, dente=16,
        regioes=[Regiao.MESIAL, Regiao.OCLUSAL], status=StatusLancamento.REALIZADO,
        data=date(2024, 6, 25), valor=Decimal("180.00"),
    )
    sessao.flush()
    return clinica, usuario, paciente


def test_gera_um_pdf_de_verdade(sessao, base):
    clinica, _, paciente = base
    conteudo = gerar(
        sessao, clinica_id=clinica.id, paciente_id=paciente.id,
        clinica_nome=clinica.nome,
    )
    assert conteudo.startswith(b"%PDF")
    assert len(conteudo) > 800


def test_paciente_sem_historico_ainda_gera_pdf(sessao, base):
    """Ficha nova tambem tem de poder ser impressa."""
    clinica, _, _ = base
    novo = Paciente(clinica_id=clinica.id, nome="Sem Historico")
    sessao.add(novo)
    sessao.flush()
    assert gerar(
        sessao, clinica_id=clinica.id, paciente_id=novo.id, clinica_nome=clinica.nome
    ).startswith(b"%PDF")


def test_nome_com_acento_nao_quebra_a_geracao(sessao, base):
    """Kátia, Sant'Anna, José — o banco dela e cheio deles."""
    clinica, _, _ = base
    p = Paciente(clinica_id=clinica.id, nome="José Carlos Sant'Anna Küçük")
    sessao.add(p)
    sessao.flush()
    assert gerar(
        sessao, clinica_id=clinica.id, paciente_id=p.id, clinica_nome=clinica.nome
    ).startswith(b"%PDF")


def test_paciente_de_outra_clinica_e_recusado(sessao, base):
    clinica, _, _ = base
    outra = Clinica(nome="Outra")
    sessao.add(outra)
    sessao.flush()
    alheio = Paciente(clinica_id=outra.id, nome="Alheio")
    sessao.add(alheio)
    sessao.flush()
    with pytest.raises(LookupError):
        gerar(
            sessao, clinica_id=clinica.id, paciente_id=alheio.id,
            clinica_nome=clinica.nome,
        )


def test_a_rota_devolve_o_pdf_como_anexo(sessao, base):
    clinica, usuario, paciente = base
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario))
        resposta = c.get(f"/prontuario/{paciente.id}.pdf")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "application/pdf"
    assert "attachment" in resposta.headers["content-disposition"]
    assert resposta.content.startswith(b"%PDF")


def test_a_rota_exige_sessao(sessao, base):
    _, _, paciente = base
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as anonimo:
        assert anonimo.get(f"/prontuario/{paciente.id}.pdf").status_code == 303
