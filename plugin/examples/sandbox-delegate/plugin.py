"""A minimal installable plugin; customize judge() for your trusted implementation."""
from app.plugin_sdk import JudgeRequest, JudgeResult


class Plugin:
    def __init__(self, context):
        self.context = context

    def judge(self, request: JudgeRequest) -> JudgeResult:
        return self.context.run_custom(request)
