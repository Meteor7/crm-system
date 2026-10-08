import unittest
from copy import deepcopy

from rayher_crm.services import blue_sheet_rules as rules


def sample_rules():
    # Test-only mapping, never installed as a production default.
    return {"version": "test-v1", "rules": [{"id": "supported", "level": "upside",
        "requiredRoles": ["Economic Buyer"], "supportingRoles": ["Economic Buyer"],
        "maxOpenRedFlags": 1, "maxHighRedFlags": 0, "maxOpposedStakeholders": 0,
        "requireClassifiedRedFlags": True, "reason": "Test rule: buyer supports and no high risks"}]}


class TestBlueSheetRules(unittest.TestCase):
    def test_legacy_duplicates_long_unicode_and_identity_are_preserved(self):
        text = "风险" * 3000
        flags = rules.red_flags("O-1", None, [text, text])
        self.assertEqual([row["text"] for row in flags], [text, text])
        self.assertEqual(len({row["id"] for row in flags}), 2)
        self.assertEqual(flags, rules.red_flags("O-1", None, [text, text]))
        self.assertNotEqual(flags[0]["id"], rules.red_flags("O-2", None, [text])[0]["id"])
        self.assertTrue(all(row["severity"] == "" and row["updatedAt"] is None for row in flags))
        self.assertEqual(rules.red_flags("O-1", [], [text]), [])

    def test_old_text_editor_retains_occurrence_state_and_new_text_starts_unknown(self):
        flags = rules.red_flags("O", None, ["Buyer missing", "Buyer missing"])
        flags[0].update(severity="High", status="Resolved")
        result = rules.reconcile_legacy(flags, ["Buyer missing", "New risk", "Buyer missing"], lambda: "new", "now", "sales")
        self.assertEqual(result[0], flags[0])
        self.assertEqual(result[2], flags[1])
        self.assertEqual((result[1]["severity"], result[1]["status"]), ("", "Open"))

    def test_updates_use_server_ids_and_audit_metadata(self):
        flags = rules.red_flags("O", None, ["Risk"])
        item = {key: flags[0][key] for key in ("id", "text", "severity", "status")}
        self.assertEqual(rules.update_flags(flags, [item], lambda: "new", "now", "sales"), flags)
        result = rules.update_flags(flags, [{**item, "severity": "High", "status": "Resolved"}], lambda: "new", "now", "sales")
        self.assertEqual(result[0]["id"], flags[0]["id"])
        self.assertEqual((result[0]["updatedAt"], result[0]["updatedBy"]), ("now", "sales"))
        for raw in ([{**item, "updatedBy": "other"}], [{**item, "id": "forged"}], [item, item], [{**item, "status": "Closed"}], [{**item, "text": " "}]):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                rules.update_flags(flags, raw, lambda: "new", "now", "sales")

    def test_large_legacy_lists_and_text_can_be_retained_but_not_expanded(self):
        flags = rules.red_flags("O", None, ["x" * 5000] * 201)
        items = [{key: row[key] for key in ("id", "text", "severity", "status")} for row in flags]
        self.assertEqual(rules.update_flags(flags, items, lambda: "new", "now", "sales"), flags)
        with self.assertRaises(ValueError):
            rules.update_flags(flags, items + [{"text": "new", "severity": "", "status": "Open"}], lambda: "new", "now", "sales")

    def test_missing_invalid_configuration_never_invents_a_level(self):
        invalid = sample_rules()
        invalid["rules"][0]["maxHighRedFlags"] = True
        for config in (None, {}, {"version": "x", "rules": []}, invalid):
            result = rules.assess([], [], config)
            self.assertEqual((result["state"], result["suggestedLevel"]), ("unconfigured", None))

    def test_legacy_editor_enforces_new_limits_and_preserves_large_existing_records(self):
        for texts in (["risk"] * 201, ["x" * 4001]):
            with self.subTest(texts=len(texts)), self.assertRaises(ValueError):
                rules.reconcile_legacy([], texts, lambda: "new", "now", "sales")
        texts = ["  Old risk\nwith detail  " + "x" * 4001] * 201
        records = rules.red_flags("O", None, texts)
        records[0].update(severity="High", status="Resolved")
        self.assertEqual(rules.reconcile_legacy(records, texts, lambda: "new", "now", "sales"), records)
        self.assertEqual(rules.reconcile_legacy(records, texts[:-1], lambda: "new", "now", "sales"), records[:-1])
        with self.assertRaises(ValueError):
            rules.reconcile_legacy(records, texts + ["New"], lambda: "new", "now", "sales")

    def test_assessment_is_deterministic_and_unknown_severity_blocks_strict_rule(self):
        people = [{"name": "S", "role": "Economic Buyer", "stance": "Support"}]
        flags = rules.red_flags("O", None, ["Risk"])
        config = sample_rules()
        self.assertEqual(rules.assess(flags, people, config)["state"], "no_match")
        flags[0]["severity"] = "Low"
        result = rules.assess(flags, people, config)
        self.assertEqual(result, rules.assess(deepcopy(flags), deepcopy(people), deepcopy(config)))
        self.assertEqual((result["suggestedLevel"], result["ruleVersion"]), ("upside", "test-v1"))
        flags[0]["severity"] = "High"
        self.assertEqual(rules.assess(flags, people, config)["state"], "no_match")
        flags[0]["status"] = "Resolved"
        self.assertEqual(rules.assess(flags, people, config)["suggestedLevel"], "upside")
        people[0]["stance"] = "Against"
        self.assertEqual(rules.assess(flags, people, config)["state"], "no_match")

    def test_fingerprint_covers_rule_version_and_facts(self):
        first = {"rules": sample_rules(), "facts": ["one"]}
        self.assertEqual(rules.fingerprint(first), rules.fingerprint(deepcopy(first)))
        changed = deepcopy(first)
        changed["rules"]["version"] = "test-v2"
        self.assertNotEqual(rules.fingerprint(first), rules.fingerprint(changed))
        changed = deepcopy(first)
        changed["facts"] = ["two"]
        self.assertNotEqual(rules.fingerprint(first), rules.fingerprint(changed))
