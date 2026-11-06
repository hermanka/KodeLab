import pytest

from app.contracts import Case, CaseResult, JudgeResult, SubmitRequest
from app.judging import public_result
from app.providers import choose_provider, provider_for
from runner.engine import tokens_equal


def test_token_checker_preserves_boundaries():
    assert tokens_equal("5 \n", "5")
    assert not tokens_equal("1 2", "12")
    assert not tokens_equal("Answer: 5", "5")


def test_hidden_case_output_is_not_exposed():
    cases = [Case(id="a", input="2 3", expected="5", public=True),
             Case(id="b", input="secret", expected="hidden")]
    result = JudgeResult(verdict="WRONG_ANSWER", cases=[
        CaseResult(id="a", verdict="ACCEPTED", stdout="5"),
        CaseResult(id="b", verdict="WRONG_ANSWER", stdout="secret", stderr="hidden")])
    visible = public_result(result, cases, "judge")
    assert visible["score"] == 0
    assert visible["passed_tests"] == 1
    assert visible["cases"][1] == {"id": "b", "verdict": "WRONG_ANSWER"}


def test_incomplete_results_are_infrastructure_failure():
    with pytest.raises(ValueError, match="Incomplete"):
        public_result(JudgeResult(verdict="ACCEPTED"), [Case(id="a", input="", expected="")], "judge")


def test_inconsistent_accepted_results_rejected():
    with pytest.raises(ValueError, match="Inconsistent"):
        public_result(JudgeResult(verdict="ACCEPTED", cases=[
            CaseResult(id="a", verdict="WRONG_ANSWER")]), [Case(id="a", input="", expected="")], "judge")


def test_run_has_no_grade():
    result = public_result(JudgeResult(verdict="EXECUTED", cases=[
        CaseResult(id="a", verdict="EXECUTED", stdout="hello")]), [Case(id="a", input="")], "run")
    assert result["score"] is None
    assert result["cases"][0]["stdout"] == "hello"


def test_provider_precedence_and_domjudge_is_honest(monkeypatch):
    monkeypatch.setenv("DEFAULT_PROVIDER", "custom")
    assert choose_provider(None, None) == "custom"
    assert choose_provider(None, None, "domjudge") == "domjudge"
    assert choose_provider(None, "custom", "domjudge") == "custom"
    assert choose_provider("domjudge", "custom") == "domjudge"
    assert not provider_for("domjudge").capabilities()["implemented"]


def test_source_limit_is_utf8_bytes():
    with pytest.raises(ValueError):
        SubmitRequest(language="c17", source="é" * 20000)
    with pytest.raises(ValueError):
        SubmitRequest(language="cpp20", source="int main(){}")
