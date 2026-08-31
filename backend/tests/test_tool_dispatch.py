"""도구 디스패치 + 스키마 검증 테스트."""

import json

from unittest.mock import MagicMock

from app.agent.tools import TOOL_DEFINITIONS, execute_tool
from app.agent.tools.write import WRITE_TOOL_NAMES


class TestToolDefinitions:
    """TOOL_DEFINITIONS 가 Claude 프로토콜에 맞는 형식인지."""

    def test_ten_tools_defined(self):
        assert len(TOOL_DEFINITIONS) == 10

    def test_all_have_required_fields(self):
        for td in TOOL_DEFINITIONS:
            assert "name" in td
            assert "description" in td
            assert "input_schema" in td
            assert td["input_schema"]["type"] == "object"

    def test_tool_names_match_dispatch(self):
        defined_names = {td["name"] for td in TOOL_DEFINITIONS}
        expected = {
            "search_applications", "get_application", "list_postings",
            "list_availability", "get_schedule_status", "list_interviews",
            "change_stage", "create_schedule_proposal",
            "assign_interviewer", "draft_email",
        }
        assert defined_names == expected

    def test_write_tools_are_subset(self):
        all_names = {td["name"] for td in TOOL_DEFINITIONS}
        assert WRITE_TOOL_NAMES.issubset(all_names)

    def test_write_tool_names(self):
        assert WRITE_TOOL_NAMES == {
            "change_stage", "assign_interviewer", "draft_email",
            "create_schedule_proposal",
        }


class TestExecuteTool:
    def test_unknown_tool_returns_error(self):
        db = MagicMock()
        user = MagicMock()
        result = json.loads(execute_tool("nonexistent_tool", {}, db, user))
        assert "error" in result
        assert "알 수 없는 도구" in result["error"]

    def test_returns_json_string(self):
        db = MagicMock()
        user = MagicMock()
        result = execute_tool("nonexistent_tool", {}, db, user)
        assert isinstance(result, str)
        json.loads(result)
