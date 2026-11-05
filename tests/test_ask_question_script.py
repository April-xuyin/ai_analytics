import runpy
from pathlib import Path


def test_ask_question_script_has_main_entrypoint() -> None:
    script = Path(__file__).parents[1] / "scripts" / "ask_question.py"
    namespace = runpy.run_path(str(script), run_name="not_main")
    assert callable(namespace["main"])
    assert callable(namespace["load_env_file"])

