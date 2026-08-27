"""A lista abre por quem foi atendido por ultimo.

Consequencia registrada no AGENTS.md e real: a busca corta em 100 resultados
DEPOIS do ORDER BY, entao trocar a ordem troca QUAIS 100 aparecem. Quem nunca foi
atendido cai para o fim (`nulls_last`) e sai da primeira tela.
"""

from app.pacientes.service import Ordem


def test_a_ordem_padrao_e_por_atendimento():
    from inspect import signature

    from app.pacientes.service import buscar

    assert signature(buscar).parameters["ordem"].default is Ordem.ATENDIMENTO


def test_a_rota_abre_na_mesma_ordem_que_a_service():
    from inspect import signature

    from app.pacientes.rotas import listar

    padrao = signature(listar).parameters["ordem"].default
    assert getattr(padrao, "default", padrao) == Ordem.ATENDIMENTO.value


def test_ordem_inventada_na_url_cai_no_padrao_e_nao_derruba_a_tela():
    fonte = (
        __import__("pathlib").Path("app/pacientes/rotas.py")
        .read_text(encoding="utf-8")
    )
    assert "Ordem.ALFABETICA" not in fonte, (
        "o fallback da rota ficou na ordem antiga e diverge do padrao"
    )
