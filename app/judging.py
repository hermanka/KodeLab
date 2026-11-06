from app.contracts import JudgeResult


def public_result(result: JudgeResult, cases, mode: str):
    by_id = {case.id: case for case in cases}
    expected_ids = set(by_id)
    received_ids = [item.id for item in result.cases]
    if result.verdict == "COMPILATION_ERROR":
        if result.cases:
            raise ValueError("Compilation failure cannot contain executed cases")
    else:
        if len(received_ids) != len(expected_ids) or set(received_ids) != expected_ids:
            raise ValueError("Incomplete or duplicate case results")
        if mode == "judge":
            allowed = {"ACCEPTED", "WRONG_ANSWER", "RUNTIME_ERROR", "TIME_LIMIT_EXCEEDED",
                       "MEMORY_LIMIT_EXCEEDED", "OUTPUT_LIMIT_EXCEEDED"}
            if any(item.verdict not in allowed for item in result.cases):
                raise ValueError("Invalid judge case verdict")
            aggregate = next((item.verdict for item in result.cases if item.verdict != "ACCEPTED"), "ACCEPTED")
            if result.verdict != aggregate:
                raise ValueError("Inconsistent aggregate verdict")
        elif result.verdict not in {"EXECUTED", "RUNTIME_ERROR", "TIME_LIMIT_EXCEEDED",
                                    "MEMORY_LIMIT_EXCEEDED", "OUTPUT_LIMIT_EXCEEDED"}:
            raise ValueError("Invalid run verdict")
    passed = sum(item.verdict == "ACCEPTED" for item in result.cases)
    visible = []
    for item in result.cases:
        case = by_id[item.id]
        row = {"id": item.id, "verdict": item.verdict}
        if mode == "run" or case.public:
            row.update(stdout=item.stdout, stderr=item.stderr, time_ms=item.time_ms,
                       input=case.input, expected=case.expected)
        visible.append(row)
    return {
        "verdict": result.verdict,
        "score": (100 if result.verdict == "ACCEPTED" else 0) if mode == "judge" else None,
        "passed_tests": passed if mode == "judge" and result.cases else None,
        "total_tests": len(cases) if mode == "judge" else None,
        "compile_log": result.compile_log, "cases": visible, "environment": result.environment,
    }
