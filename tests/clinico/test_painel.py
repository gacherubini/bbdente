import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.models import Clinica
from app.auth.service import criar_usuario
from app.auth.sessao import NOME_COOKIE, assinar
from app.catalogo.models import Categoria, Procedimento
from app.main import criar_app
from app.pacientes.models import Paciente
from app.shared.db import obter_sessao
from app.shared.tipos import Escopo, Regiao, StatusLancamento

PAINEL = Path("app/templates/_painel_lancamento.html")
JS = Path("app/static/painel.js")


@pytest.fixture
def cliente(sessao):
    clinica = Clinica(nome="C")
    sessao.add(clinica)
    sessao.flush()
    usuario = criar_usuario(
        sessao, clinica_id=clinica.id, email="k@e.com", senha="senha-longa", nome="K"
    )
    categoria = Categoria(clinica_id=clinica.id, codigo="04", nome="Dentistica", ordem=4)
    paciente = Paciente(clinica_id=clinica.id, nome="Amanda")
    sessao.add_all([categoria, paciente])
    sessao.flush()
    proc = Procedimento(
        clinica_id=clinica.id, codigo="21", nome="Restauracao Classe II",
        categoria_id=categoria.id, escopo_sugerido=Escopo.REGIOES,
        regioes_sugeridas=[Regiao.MESIAL, Regiao.OCLUSAL],
    )
    sessao.add(proc)
    sessao.flush()
    app = criar_app()
    app.dependency_overrides[obter_sessao] = lambda: sessao
    with TestClient(app, follow_redirects=False) as c:
        c.cookies.set(NOME_COOKIE, assinar(usuario))
        yield c, paciente, proc


def test_o_painel_fica_ao_lado_do_odontograma_sempre_visivel(cliente):
    """Nao e modal nem outra tela: ela precisa ver o dente enquanto lanca."""
    c, paciente, _ = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    assert 'class="odonto-area"' in html
    assert html.index('id="odontograma"') < html.index('id="painel"')


def test_o_painel_traz_as_categorias_e_os_tratamentos(cliente):
    c, paciente, _ = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    assert "Dentistica" in html or "Dentística" in html
    assert "Restauracao Classe II" in html


def test_as_oito_regioes_aparecem_como_caixas_marcaveis(cliente):
    c, paciente, _ = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    for regiao in Regiao:
        assert f'value="{regiao.value}"' in html


def test_o_painel_oferece_planejado_e_realizado(cliente):
    c, paciente, _ = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    for status in StatusLancamento:
        assert f'value="{status.value}"' in html


def test_o_botao_repetir_em_outro_dente_existe(cliente):
    """46% das consultas com mais de um lancamento repetem o mesmo tratamento."""
    c, paciente, _ = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    assert "Repetir em outro dente" in html


def test_o_sugerido_do_procedimento_viaja_para_a_tela(cliente):
    c, paciente, proc = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    bruto = re.search(r'id="catalogo"[^>]*>(.*?)</script>', html, re.S)
    assert bruto
    import json

    catalogo = json.loads(bruto.group(1))
    achado = next(
        p for cat in catalogo for p in cat["procedimentos"] if p["id"] == proc.id
    )
    assert achado["escopo_sugerido"] == "REGIOES"
    assert achado["regioes_sugeridas"] == ["MESIAL", "OCLUSAL"]


# --- contrato do JS ------------------------------------------------------------

def test_o_js_pre_marca_o_sugerido_mas_nao_impede_mudar():
    """A tela sugere, nao impoe: qualquer tratamento pode ir em qualquer regiao."""
    fonte = JS.read_text(encoding="utf-8")
    assert "regioes_sugeridas" in fonte
    # O JS so desabilita os botoes e o seletor de tratamento. As caixas de regiao
    # e os radios de escopo NUNCA sao desabilitados: a sugestao vem marcada, mas
    # ela pode desmarcar tudo e escolher outra coisa.
    permitidos = ("painel-lancar", "painel-repetir", "seletor")
    for linha in fonte.splitlines():
        if "disabled" in linha:
            assert any(nome in linha for nome in permitidos), linha


def test_o_js_manda_o_lancamento_para_a_api_certa():
    fonte = JS.read_text(encoding="utf-8")
    assert "/api/lancamento" in fonte
    assert "atualizar" in fonte  # redesenha o odontograma com o estado devolvido


def test_o_js_trata_erro_da_api_em_vez_de_falhar_calado():
    fonte = JS.read_text(encoding="utf-8")
    assert "catch" in fonte


# --- a data ja vem preenchida com hoje ------------------------------------------


def test_a_data_do_painel_ja_vem_com_hoje(cliente):
    """Quem esta com o paciente na cadeira lanca o que esta fazendo agora. Deixar
    o campo vazio grava lancamento sem data — foi assim que apareceu um grupo
    'Sem data' no historico de quem nunca digitou data nenhuma."""
    from datetime import date

    c, paciente, _ = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    assert f'id="painel-data" value="{date.today().isoformat()}"' in html


def test_a_data_ja_vem_com_hoje_tambem_no_atendimento_sem_paciente(cliente):
    from datetime import date

    c, _, _ = cliente
    html = c.get("/odontograma").text
    assert f'id="painel-data" value="{date.today().isoformat()}"' in html


def test_a_data_continua_editavel(cliente):
    """Preencher com hoje e um padrao, nao uma trava."""
    c, paciente, _ = cliente
    html = c.get(f"/odontograma/{paciente.id}").text
    campo = re.search(r'<input type="date" id="painel-data"[^>]*>', html).group(0)
    assert "readonly" not in campo
    assert "disabled" not in campo
