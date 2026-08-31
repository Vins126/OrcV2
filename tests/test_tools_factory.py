"""La factory dei tool non usa stato globale e rispetta il workspace richiesto."""

from tools import build_default_tools


def test_factory_crea_tool_distinti_nel_workspace_passato(tmp_path):
    tools = build_default_tools(str(tmp_path / "worker-a"))

    assert [tool.name for tool in tools] == ["bash", "read_file", "write_file"]
    assert (tmp_path / "worker-a").is_dir()
