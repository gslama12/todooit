from pathlib import Path

from tests.features import FEATURE_BY_MODULE


def test_every_test_module_has_a_feature():
    """
    A new test file belongs to a feature group from the day it is added

    The groups are derived from filenames, so a file nobody adds to the table
    is still collected and still run — it just quietly answers to no `-m`
    selection, which is the kind of gap that is only ever noticed later.
    """

    root = Path(__file__).parent
    missing = sorted(
        path.stem
        for path in root.rglob("test_*.py")
        if path.stem != "test_meta" and path.stem not in FEATURE_BY_MODULE
    )

    assert not missing, (
        f"add these to FEATURE_BY_MODULE in tests/features.py: {missing}"
    )
