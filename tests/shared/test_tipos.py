from app.shared.tipos import (
    REGIOES_COROA,
    REGIOES_RAIZ,
    Escopo,
    Regiao,
    StatusLancamento,
    TipoCondicao,
)


def test_coroa_e_raiz_particionam_as_regioes():
    """Toda regiao pertence a exatamente um dos dois grupos — sem sobra, sem falta."""
    assert REGIOES_COROA | REGIOES_RAIZ == set(Regiao)
    assert REGIOES_COROA & REGIOES_RAIZ == set()


def test_grupos_tem_os_tamanhos_da_spec():
    assert len(REGIOES_COROA) == 5
    assert len(REGIOES_RAIZ) == 3


def test_enums_serializam_como_o_proprio_nome():
    """Sao StrEnum: o valor gravado no banco e o nome, sem traducao no meio."""
    assert Escopo.REGIOES == "REGIOES"
    assert Regiao.CANAL_MESIAL == "CANAL_MESIAL"
    assert StatusLancamento.PLANEJADO == "PLANEJADO"
    assert TipoCondicao.AUSENTE == "AUSENTE"
    for membro in (*Escopo, *Regiao, *StatusLancamento, *TipoCondicao):
        assert membro.value == membro.name
