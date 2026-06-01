import re

from guardrails.dangerous_commands import DANGEROUS_COMMAND_PATTERNS


def test_all_dangerous_patterns_compile():
    for code, _name, pattern, _score in DANGEROUS_COMMAND_PATTERNS:
        re.compile(pattern)


def test_drop_table_matches():
    pattern = next(p[2] for p in DANGEROUS_COMMAND_PATTERNS if p[0] == "drop_sql")
    assert re.search(pattern, "DROP TABLE Users;", re.IGNORECASE)
