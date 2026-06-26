import unittest
from datetime import date, datetime

from pydantic import ValidationError

from tests.b1_fixtures import (
    make_backtest_universe,
    make_forward_watchlist,
    make_gate_result,
    make_protocol_snapshot,
    make_strategy_draft,
    make_template_definition,
)


class TestB1FrozenContracts(unittest.TestCase):
    def test_template_definition_is_frozen(self):
        template = make_template_definition()
        with self.assertRaises(ValidationError):
            template.version = "v2"

    def test_strategy_draft_is_frozen_and_stays_draft_content(self):
        draft = make_strategy_draft()
        self.assertFalse(hasattr(draft, "status"))
        with self.assertRaises(ValidationError):
            draft.strategy_template_id = "another_template"

    def test_protocol_requires_all_three_hashes(self):
        data = make_protocol_snapshot().model_dump()
        data["strategy_config_hash"] = ""
        with self.assertRaisesRegex(ValidationError, "strategy_config_hash"):
            type(make_protocol_snapshot()).model_validate(data)

    def test_gate_v2_rejects_prototype_passed_verdict(self):
        data = make_gate_result().model_dump()
        data["verdict"] = "prototype_passed"
        with self.assertRaises(ValidationError):
            type(make_gate_result()).model_validate(data)

    def test_universe_types_are_not_convertible(self):
        watchlist = make_forward_watchlist()
        with self.assertRaises(ValidationError):
            type(make_backtest_universe()).model_validate(watchlist.model_dump())

    def test_revision_id_is_required_but_not_generated(self):
        data = make_strategy_draft().model_dump()
        data["strategy_revision_id"] = ""
        with self.assertRaisesRegex(ValidationError, "strategy_revision_id"):
            type(make_strategy_draft()).model_validate(data)


if __name__ == "__main__":
    unittest.main()
