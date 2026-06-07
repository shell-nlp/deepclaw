from pathlib import Path


def test_tests_directory_has_no_unittest_framework_usage():
    tests_dir = Path(__file__).parent
    offenders: list[str] = []

    banned_patterns = (
        "import unittest",
        "unittest.TestCase",
        "unittest.IsolatedAsyncioTestCase",
        "self.assert",
        "unittest.main()",
    )

    for path in sorted(tests_dir.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue
        content = path.read_text(encoding="utf-8")
        for pattern in banned_patterns:
            if pattern in content:
                offenders.append(f"{path.name}: {pattern}")

    assert offenders == []
