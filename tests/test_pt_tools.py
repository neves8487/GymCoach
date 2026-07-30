"""
Unit tests for PT tools.
"""

from unittest.mock import MagicMock, patch
import pytest

from gym_coach.tools.pt_tools import (
    get_historico_exercicio,
    guardar_plano_treino,
    obter_plano_treino,
    registar_treino,
)


@pytest.fixture
def mock_tool_context():
    context = MagicMock()
    context.state = {"user_phone": "+351912345678"}
    return context


@patch("gym_coach.tools.pt_tools.db.get_recent_workouts")
def test_get_historico_exercicio_general(mock_get_recent, mock_tool_context):
    mock_get_recent.return_value = [
        {"exercicio": "Remada Bent Over", "data": "2026-07-29T14:00:00"},
        {"exercicio": "Lat Pulldown", "data": "2026-07-29T14:05:00"},
    ]

    res = get_historico_exercicio(tool_context=mock_tool_context, exercicio=None, ultimas_n=10)

    assert res["exercicio"] == "todos"
    assert res["total_sessoes"] == 2
    mock_get_recent.assert_called_once_with(
        phone="+351912345678",
        exercicio=None,
        limit=10,
    )


@patch("gym_coach.tools.pt_tools.db.get_recent_workouts")
def test_get_historico_exercicio_specific(mock_get_recent, mock_tool_context):
    mock_get_recent.return_value = [
        {"exercicio": "remada", "data": "2026-07-29T14:00:00"},
    ]

    res = get_historico_exercicio(tool_context=mock_tool_context, exercicio="remada", ultimas_n=5)

    assert res["exercicio"] == "remada"
    assert res["total_sessoes"] == 1
    mock_get_recent.assert_called_once_with(
        phone="+351912345678",
        exercicio="remada",
        limit=5,
    )


@patch("gym_coach.tools.pt_tools.db.save_workout_plan")
def test_guardar_plano_treino(mock_save_plan, mock_tool_context):
    mock_save_plan.return_value = "quarta"

    exercicios = [
        {"nome": "Remada Bent Over", "peso": 80, "sets": 3, "reps": 8, "rpe_alvo": 8.5}
    ]
    res = guardar_plano_treino(
        dia_semana="quarta",
        nome_treino="Costas e Bíceps",
        exercicios=exercicios,
        tool_context=mock_tool_context,
    )

    assert res["status"] == "plano_guardado"
    assert res["dia_semana"] == "quarta"
    assert res["total_exercicios"] == 1
    mock_save_plan.assert_called_once()


@patch("gym_coach.tools.pt_tools.db.get_workout_plan")
def test_obter_plano_treino(mock_get_plan, mock_tool_context):
    mock_get_plan.return_value = [
        {"dia_semana": "quarta", "nome_treino": "Costas e Bíceps"}
    ]

    res = obter_plano_treino(tool_context=mock_tool_context, dia_semana="quarta")

    assert res["total_planos"] == 1
    mock_get_plan.assert_called_once_with("+351912345678", "quarta")


@patch("gym_coach.tools.pt_tools.db.add_workout")
def test_registar_treino(mock_add_workout, mock_tool_context):
    mock_add_workout.return_value = "doc_123"

    series = [{"peso": 80, "reps": 8, "rpe": 8.5, "falhou": False}]
    res = registar_treino(
        exercicio="Remada Bent Over",
        series=series,
        notas="Fiz tudo o pedido",
        dor_reportada=False,
        tool_context=mock_tool_context,
    )

    assert res["status"] == "registado"
    assert res["exercicio"] == "Remada Bent Over"
    assert res["analise"]["rpe_ultimo_set"] == 8.5
