import re
from pathlib import Path

CSS = Path("app/static/bddente.css")
BASE = Path("app/templates/base.html")

TOKENS = {
    "--roxo": "#7C3AED",
    "--roxo-esc": "#5B21B6",
    "--roxo-cl": "#EDE9FE",
    "--roxo-brd": "#C4B5FD",
    "--borda": "#E2E8F0",
    "--texto": "#0F172A",
    "--texto-fraco": "#64748B",
    "--planejado": "#DC2626",
    "--realizado": "#16A34A",
    "--existente": "#2563EB",
}


def test_todos_os_tokens_da_spec_estao_definidos():
    css = CSS.read_text(encoding="utf-8")
    for nome, valor in TOKENS.items():
        assert re.search(rf"{re.escape(nome)}\s*:\s*{valor}", css, re.I), nome


def test_o_fundo_da_pagina_e_branco_nao_roxo():
    """A spec e explicita: interface branca com roxo nos detalhes."""
    css = CSS.read_text(encoding="utf-8")
    corpo = re.search(r"\bbody\s*\{([^}]*)\}", css, re.S)
    assert corpo, "regra para body nao encontrada"
    assert re.search(r"background\s*:\s*#fff", corpo.group(1), re.I)


def test_o_nome_aparece_em_branco_sobre_a_lateral_roxa():
    css = CSS.read_text(encoding="utf-8")
    marca = re.search(r"\.marca\s*\{([^}]*)\}", css, re.S)
    assert marca and re.search(r"color\s*:\s*#fff", marca.group(1), re.I)
    lateral = re.search(r"\.lateral\s*\{([^}]*)\}", css, re.S)
    assert lateral and "roxo" in lateral.group(1)


def test_a_navegacao_tem_as_cinco_abas():
    html = BASE.read_text(encoding="utf-8")
    for rotulo in ("Pacientes", "Odontograma", "Atendimentos", "Tratamentos", "Financeiro"):
        assert rotulo in html


def test_atendimentos_fica_ao_lado_do_odontograma():
    """Quem conclui um atendimento cai no odontograma; ver o dia e o passo
    seguinte, entao as duas abas ficam vizinhas."""
    html = BASE.read_text(encoding="utf-8")
    assert html.index('href="/odontograma"') < html.index('href="/atendimentos"')
    assert html.index('href="/atendimentos"') < html.index('href="/tratamentos"')


def test_nenhuma_aba_promete_o_que_ainda_nao_existe():
    """O Financeiro dizia 'em breve' desde o MVP. Agora existe."""
    html = BASE.read_text(encoding="utf-8")
    assert "em breve" not in html
    assert 'href="/financeiro"' in html


def test_o_layout_expoe_os_blocos_que_as_telas_usam():
    html = BASE.read_text(encoding="utf-8")
    for bloco in ("titulo", "conteudo", "scripts"):
        assert f"block {bloco}" in html


def test_a_pagina_declara_idioma_e_viewport():
    html = BASE.read_text(encoding="utf-8")
    assert 'lang="pt-BR"' in html
    assert "viewport" in html


def test_a_lateral_fica_presa_na_janela_nao_no_documento():
    """O bug: `.lateral` era filha flex de `.app{min-height:100vh}`, entao crescia
    ate a altura do DOCUMENTO. O "Sair", empurrado para o fim dessa coluna, nascia
    no rodape da pagina inteira — fora da tela em qualquer pagina comprida, como o
    odontograma. Nao dava para deslogar sem rolar ate o fim.

    Presa na janela, o menu e o "Sair" ficam sempre visiveis.
    """
    css = CSS.read_text(encoding="utf-8")
    lateral = re.search(r"\.lateral\s*\{([^}]*)\}", css, re.S)
    assert lateral, "regra para .lateral nao encontrada"
    regra = lateral.group(1)
    assert re.search(r"position\s*:\s*sticky", regra), "a lateral precisa ser sticky"
    assert re.search(r"top\s*:\s*0", regra)
    assert re.search(r"height\s*:\s*100vh", regra), (
        "a altura tem de ser a da janela, nao a do documento"
    )
    assert re.search(r"overflow-y\s*:\s*auto", regra), (
        "menu maior que a janela precisa rolar dentro da lateral"
    )


def test_o_conteudo_tem_largura_maxima_e_fica_centralizado():
    """Sem teto, o odontograma e o painel de lancamento sao arrastados para cantos
    opostos de um monitor largo."""
    css = CSS.read_text(encoding="utf-8")
    faixa = re.search(r"\.faixa\s*\{([^}]*)\}", css, re.S)
    assert faixa, "regra para .faixa nao encontrada"
    assert re.search(r"max-width\s*:", faixa.group(1))
    assert re.search(r"margin\s*:\s*0\s+auto", faixa.group(1))


def test_o_rodape_da_lateral_diz_quem_esta_logado_e_leva_ao_perfil():
    html = BASE.read_text(encoding="utf-8")
    assert "usuario.nome" in html
    assert 'href="/perfil"' in html
    assert 'action="/logout"' in html
