import pytest

from airix_cli.agent.intent import is_change_request


@pytest.mark.parametrize(
    "instruction",
    [
        "analiza deploy_yolo.py",
        "revisa el código de deploy_yolo.py",
        "haz una revisión de código de deploy_yolo.py",
        "explícame qué hace deploy_yolo.py",
        "¿qué mejoras harías en deploy_yolo.py?",
        "¿qué genera esta función?",
        "analízalo sin modificar nada",
        "revisa src/update_config.py",
        "review deploy_yolo.py",
        "dime qué cambios le harías",
    ],
)
def test_queries_are_not_change_requests(instruction):
    assert is_change_request(instruction) is False


@pytest.mark.parametrize(
    "instruction",
    [
        "corrige los errores de deploy_yolo.py",
        "analiza deploy_yolo.py y arréglalo",
        "refactoriza el parser",
        "añade logging a deploy_yolo.py",
        "¿puedes corregir el bug de deploy_yolo.py?",
        "quiero que lo corrijas",
        "no funciona, cámbialo",
        "fix the bug in deploy_yolo.py",
    ],
)
def test_modification_requests_are_change_requests(instruction):
    assert is_change_request(instruction) is True
