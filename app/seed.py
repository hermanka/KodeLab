from app.db import session
from app.models import ProblemVersion, QuotaLock, TestCase

LIMITS = {"compile_seconds": 10, "time_seconds": 2, "memory_mb": 128, "output_bytes": 65536}


def seed():
    with session() as db, db.begin():
        if not db.get(QuotaLock, "admission"):
            db.add(QuotaLock(id="admission"))
        if db.get(ProblemVersion, "sum-v1"):
            return
        db.add(ProblemVersion(
            id="sum-v1", title="Penjumlahan dua bilangan",
            statement="Baca dua bilangan bulat (-1000000 sampai 1000000), lalu cetak jumlahnya. Jangan cetak prompt input.",
            languages=["c17", "cpp17"], limits=LIMITS,
            scoring_policy="binary-v1", checker="tokens-v1", status="published",
        ))
        db.flush()
        for position, (input_text, expected) in enumerate([
            ("2 3\n", "5\n"), ("0 0\n", "0\n"), ("-5 2\n", "-3\n"),
            ("-7 -8\n", "-15\n"), ("1000000 1000000\n", "2000000\n"),
        ], 1):
            db.add(TestCase(problem_version_id="sum-v1", position=position,
                            input=input_text, expected=expected, public=(position == 1)))


if __name__ == "__main__":
    seed()
    print("Seed sum-v1 ready (C17 and C++17).")
