"""API v1 available to trusted judging plugins."""
from app.contracts import Case, CaseResult, JudgeRequest, JudgeResult


class ProviderUnavailable(Exception):
    pass


class PluginContext:
    def run_custom(self, request: JudgeRequest) -> JudgeResult:
        """Compile/run through the isolated runner; never execute learner code here."""
        from plugin.custom.provider import CustomProvider
        provider = CustomProvider()
        reference = provider.submit(request, str(request.attempt_id))
        return provider.get_result(reference)
