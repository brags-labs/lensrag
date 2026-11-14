import unittest
from lensrag.planning import plan_query, build_scopes, parse_periods, period_range, overlaps

INV = {"domain": "hr",
       "entities": {"country": [{"value": c, "name": n} for c, n in [("DE", "Germany"), ("IN", "India"), ("NL", "Netherlands"),
                                                                     ("UK", "United Kingdom"), ("US", "United States")]],
                    "office": [{"value": o, "name": o, "parent": c} for o, c in [("Bengaluru", "IN"), ("Berlin", "DE"),
                                                                                ("Singapore", "SG")]]},
       "versions": ["1.0", "2.0", "3.0"], "periods": []}


class PlanningTests(unittest.TestCase):
    def test_top_k_comes_from_the_question(self):
        p = plan_query("Which three countries have the highest employer retirement contribution under version 3.0?", INV)
        self.assertEqual((p.qtype, p.operation, p.k, p.direction), ("rank", "rank", 3, "desc"))
        self.assertEqual(plan_query("Show the top 2 countries by leave", INV).k, 2)

    def test_filter_threshold_and_comparator(self):
        p = plan_query("Which countries give at least 25 working days of paid annual leave under version 3.0?", INV)
        self.assertEqual((p.qtype, p.operation, p.threshold, p.comparator), ("filter", "filter", 25.0, "gte"))
        p = plan_query("In which countries do partners receive more than 2 weeks of partner leave?", INV)
        self.assertEqual((p.threshold, p.comparator), (2.0, "gt"))

    def test_extremum_direction(self):
        self.assertEqual(plan_query("Which country has the lowest paid annual leave?", INV).operation, "min")
        self.assertEqual(plan_query("Which country has the highest paid annual leave?", INV).operation, "max")

    def test_excluded_country_is_not_the_scope(self):
        p = plan_query("Excluding the Netherlands, rank the top three countries by paid sick days.", INV)
        scopes = build_scopes(p, INV)
        self.assertNotIn("NL", [s.country for s in scopes])
        self.assertEqual(len(scopes), 4)

    def test_versions_split_into_scopes(self):
        p = plan_query("For which countries did the paid annual leave change between policy version 2.0 and version 3.0?", INV)
        self.assertEqual(p.qtype, "version_diff")
        self.assertTrue(p.include_superseded)
        scopes = build_scopes(p, INV)
        self.assertEqual(len(scopes), 5 * 2)
        self.assertEqual({s.version for s in scopes}, {"2.0", "3.0"})

    def test_old_version_question_includes_superseded_documents(self):
        p = plan_query("What was the work-from-another-country allowance under version 1.0?", INV)
        self.assertEqual(p.qtype, "version_diff")
        self.assertTrue(p.include_superseded)
        self.assertFalse(plan_query("What is the sick leave in India?", INV).include_superseded)

    def test_periods_compare_and_filter(self):
        p = plan_query("How did the number of hybrid-policy grievances change from Q1 2026 to Q2 2026?", INV)
        self.assertEqual(p.qtype, "comparison")
        self.assertEqual(len(p.periods), 2)
        self.assertEqual(len(build_scopes(p, INV)), 5 * 2)
        self.assertEqual(p.doc_types, ["grievance_register"])
        one = parse_periods("between November 2025 and October 2026")
        self.assertEqual(len(one), 1)
        self.assertTrue(overlaps(period_range("2026-Q2"), one[0]))
        self.assertFalse(overlaps(period_range("2025-10"), one[0]))
        before_after = parse_periods("How did exits change after the rule took effect on 1 April 2026?")
        self.assertEqual(len(before_after), 2)

    def test_offices_are_entities(self):
        p = plan_query("Which BragsLabs offices have both an on-site gym and a creche?", INV)
        self.assertEqual(p.fanout, "office")
        self.assertEqual({s.label for s in build_scopes(p, INV)}, {"Bengaluru", "Berlin", "Singapore"})
        # In this inventory Singapore is only an office, so naming it scopes to that office.
        q = plan_query("What is the annual leave in Singapore?", INV)
        self.assertEqual((q.named, q.fanout), ({"office": ["Singapore"]}, "office"))
        # When a name is both a country and an office, it stays a country unless offices are the topic.
        both = dict(INV, entities=dict(INV["entities"], country=INV["entities"]["country"] + [{"value": "SG", "name": "Singapore"}]))
        q = plan_query("What is the annual leave in Singapore?", both)
        self.assertEqual((q.named, q.fanout), ({"country": ["SG"]}, "country"))
        r = plan_query("How many offices are there in India?", INV)
        self.assertEqual([s.label for s in build_scopes(r, INV)], ["Bengaluru"])

    def test_local_question_is_one_scope(self):
        p = plan_query("Under policy version 3.0, what is the paid annual leave for employees in Germany?", INV)
        self.assertEqual(p.qtype, "local")
        self.assertEqual([s.country for s in build_scopes(p, INV)], ["DE"])
        p = plan_query("How many office days a week must hybrid employees attend?", INV)
        self.assertEqual((p.qtype, len(build_scopes(p, INV))), ("local", 1))

    def test_llm_overrides_win_when_valid(self):
        p = plan_query("Tell me about leave", INV, {"qtype": "rank", "k": 2, "direction": "asc"})
        self.assertEqual((p.qtype, p.operation, p.k, p.direction), ("rank", "rank", 2, "asc"))
        self.assertEqual(plan_query("Tell me about leave", INV, {"qtype": "bogus"}).qtype, "local")


if __name__ == "__main__":
    unittest.main()
