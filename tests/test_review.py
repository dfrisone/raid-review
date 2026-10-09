import unittest

from raidreview import review


class ParseReport(unittest.TestCase):
    def test_full_link(self):
        self.assertEqual(review.parse_report("https://www.warcraftlogs.com/reports/mxv2fRh4J6GCAW79?boss=3420&difficulty=5&wipes=1"),
                         ("mxv2fRh4J6GCAW79", 3420, 5, "wipes"))

    def test_link_with_fight_only(self):
        self.assertEqual(review.parse_report("https://www.warcraftlogs.com/reports/mxv2fRh4J6GCAW79?fight=28&view=replay"),
                         ("mxv2fRh4J6GCAW79", None, None, None))

    def test_bare_code(self):
        self.assertEqual(review.parse_report("  mxv2fRh4J6GCAW79 "), ("mxv2fRh4J6GCAW79", None, None, None))

    def test_rejects_other_text(self):
        with self.assertRaises(ValueError):
            review.parse_report("https://example.com/whatever")


class Wipes(unittest.TestCase):
    def test_five_deaths_in_three_seconds(self):
        deaths = [{"f": 1, "ts": t} for t in (30, 60, 100, 100.5, 101, 102, 102.9, 110)]
        self.assertEqual(review._wipes(deaths, [{"id": 1, "kill": False}]), {1: 100})

    def test_slow_wipe_and_kill_have_no_moment(self):
        deaths = [{"f": 1, "ts": t} for t in (10, 20, 30, 40, 50)] + [{"f": 2, "ts": t} for t in (5, 5, 5, 5, 5)]
        self.assertEqual(review._wipes(deaths, [{"id": 1, "kill": False}, {"id": 2, "kill": True}]), {})


def death(**kw):
    d = {"kb": "Tempest", "defs": [], "ok": 0, "max": 1000, "h5": 500}
    d.update(kw)
    return d


class Judge(unittest.TestCase):
    def test_avoidable(self):
        self.assertEqual(review.judge(death(), {"Tempest"}), ["avoid"])

    def test_defensive_ready_only_when_overkill_is_coverable(self):
        ready = [{"n": "Blur", "s": "ready"}]
        self.assertIn("def", review.judge(death(defs=ready, ok=400)))
        self.assertNotIn("def", review.judge(death(defs=ready, ok=500)))
        self.assertNotIn("def", review.judge(death(defs=[{"n": "Blur", "s": "cd"}])))

    def test_no_heals_under_ten_percent(self):
        self.assertIn("heal", review.judge(death(h5=99)))
        self.assertNotIn("heal", review.judge(death(h5=100)))

    def test_no_damage_logged_skips_defensive_and_heal_checks(self):
        d = death(kb=review.NO_DAMAGE, defs=[{"n": "Blur", "s": "ready"}], h5=0)
        self.assertEqual(review.judge(d), ["ko"])


class PackEvents(unittest.TestCase):
    def test_shared_name_tables(self):
        deaths = [{"ev": [{"t": -1.0, "k": 1, "a": "Renew", "amt": 10, "abs": 0, "hp": 5, "src": "Raisyns"},
                          {"t": 0.0, "k": 0, "a": "Tempest", "amt": 90, "abs": 4, "hp": 0}]},
                  {"ev": [{"t": -2.0, "k": 0, "a": "Tempest", "amt": 50, "abs": 0, "hp": 20}]}]
        names, srcs = review._pack_events(deaths)
        self.assertEqual(names, ["Renew", "Tempest"])
        self.assertEqual(srcs, ["Raisyns"])
        self.assertEqual(deaths[0]["e"], [[-1.0, 1, 0, 10, 0, 5, 0], [0.0, 0, 1, 90, 4, 0, -1]])
        self.assertEqual(deaths[1]["e"], [[-2.0, 0, 1, 50, 0, 20, -1]])


if __name__ == "__main__":
    unittest.main()
