import json
from pathlib import Path

from gib_radar.config import Config
from gib_radar.mcp_server import Server


def make_server(tmp_path: Path) -> Server:
    cfg = Config()
    cfg.db_path = tmp_path / "radar.db"
    return Server(cfg)


def test_initialize_reports_server_info(tmp_path):
    reply = make_server(tmp_path).handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert reply["result"]["serverInfo"]["name"] == "gib-radar"
    assert "tools" in reply["result"]["capabilities"]


def test_tools_list_exposes_radar_tools(tmp_path):
    reply = make_server(tmp_path).handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in reply["result"]["tools"]}
    assert names == {"radar_top", "radar_scan", "radar_show", "radar_stats"}


def test_notifications_get_no_reply(tmp_path):
    assert make_server(tmp_path).handle(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_is_an_error(tmp_path):
    reply = make_server(tmp_path).handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})
    assert reply["error"]["code"] == -32601


def test_tool_call_returns_json_text(tmp_path):
    reply = make_server(tmp_path).handle({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "radar_stats", "arguments": {}},
    })
    payload = json.loads(reply["result"]["content"][0]["text"])
    assert payload == {"tasks": 0, "open": 0}
    assert reply["result"]["isError"] is False


def test_missing_task_is_reported_as_tool_error(tmp_path):
    reply = make_server(tmp_path).handle({
        "jsonrpc": "2.0", "id": 5, "method": "tools/call",
        "params": {"name": "radar_show", "arguments": {"task_id": "nope"}},
    })
    assert reply["error"]["code"] == -32603
    assert "radar_scan" in reply["error"]["message"]
