import yaml

import tokenplans.cli as cli


def _write_valid(path):
    path.write_text(yaml.safe_dump({
        "name": "DeepSeek", "slug": "deepseek",
        "endpoints": [{"id": "openai", "api_type": "openai",
                       "base_url": "https://api.deepseek.com", "auth": "bearer"}],
    }))


def test_validate_valid(tmp_path, capsys):
    f = tmp_path / "p.yaml"
    _write_valid(f)
    assert cli.main(["validate", str(f)]) == 0


def test_validate_invalid(tmp_path, capsys):
    f = tmp_path / "p.yaml"
    f.write_text("name: X\n")
    assert cli.main(["validate", str(f)]) == 1
    assert "slug" in capsys.readouterr().err


def test_validate_agent_file(tmp_path):
    f = tmp_path / "a.yaml"
    f.write_text(yaml.safe_dump({"name": "Claude Code", "api_type": "anthropic"}))
    assert cli.main(["validate", str(f)]) == 0


def test_validate_missing_file():
    assert cli.main(["validate", "/no/such/file.yaml"]) == 1
