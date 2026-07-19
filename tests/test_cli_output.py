import io
import json
import sys

from enterprise_rag_lab.cli import _print_json


def test_json_output_falls_back_to_ascii_on_gbk_terminal(monkeypatch) -> None:
    buffer = io.BytesIO()
    output = io.TextIOWrapper(buffer, encoding="gbk")
    monkeypatch.setattr(sys, "stdout", output)

    _print_json({"message": "中文 🔒"})
    output.flush()
    payload = buffer.getvalue().decode("ascii")

    assert json.loads(payload) == {"message": "中文 🔒"}
    assert "\\ud83d\\udd12" in payload