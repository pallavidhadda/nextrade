import ast
from pathlib import Path

import indiafacts.webui as webui

APP = Path(__file__).resolve().parent.parent / "streamlit_app.py"


def test_every_webui_function_the_streamlit_app_calls_exists():
    """The cloud deploy once crashed on webui.ownership_html. Catch a missing function before it ships."""
    tree = ast.parse(APP.read_text())
    called = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "webui"}
    missing = sorted(a for a in called if not hasattr(webui, a))
    assert not missing, missing


def test_app_prefers_checked_out_source_over_an_installed_copy():
    text = APP.read_text()
    assert "sys.path.insert(0, _ROOT)" in text and "del sys.modules[_name]" in text
