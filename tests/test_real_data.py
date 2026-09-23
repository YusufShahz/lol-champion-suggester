"""Sanity checks on the scraped data and on suggestions for real drafts (skipped without data)."""

import statistics
import time
import unittest

import champion_data as cd
import suggester as sg


@unittest.skipUnless(cd.champ_stats and cd.has_matchup_data(), "run py data/update_data.py first")
class RealDataTest(unittest.TestCase):
    def test_well_known_main_roles(self):
        mains = {"Jinx": "bottom", "Thresh": "support", "Lee Sin": "jungle", "Ahri": "middle", "Garen": "top"}
        self.assertEqual({name: cd.main_lane(name) for name in mains}, mains)

    def test_lane_averages_are_plausible(self):
        for lane in cd.LANES:
            self.assertTrue(45 < cd.lane_avg_wr(lane) < 55, lane)

    def test_every_champion_has_a_lane_and_icon(self):
        self.assertEqual([c for c in cd.champions if not cd.playable_lanes(c)], [])
        self.assertEqual([c["name"] for c in cd.champion_catalog() if not c["icon"]], [])

    def test_matchup_tables_agree(self):
        wr_offsets, d2_sums = [], []
        for a in cd.champions:
            for lane in cd.playable_lanes(a):
                for b, row in cd.lane_opponents(a, lane).items():
                    rev = cd.lane_opponents(b, lane).get(a)
                    if rev:
                        wr_offsets.append(row[0] + rev[0] - 2 * cd.lane_avg_wr(lane))
                        d2_sums.append(row[1] + rev[1])
        self.assertGreater(len(d2_sums), 1000)
        self.assertLess(abs(statistics.mean(wr_offsets)), 0.75)
        self.assertLess(abs(statistics.mean(d2_sums)), 0.5)

    def test_blind_pick_suggestions(self):
        for role in cd.ROLES:
            lane = cd.ROLE_TO_LANE[role]
            ranked = sg.rank_candidates(sg.Draft(my_lane=role))
            with self.subTest(role=role):
                self.assertGreaterEqual(len(ranked), 15)
                self.assertTrue(all(r["lane"] == lane for r in ranked))
                self.assertEqual(len({r["champion"] for r in ranked}), len(ranked))
                self.assertTrue(all(40 < r["estimate"] < 60 for r in ranked))

    def test_counter_picks_rise_against_a_known_laner(self):
        ranked = sg.rank_candidates(sg.Draft(my_lane="Mid", enemies=[("Yasuo", "Mid")]))
        top5 = statistics.mean(r["breakdown"]["matchups"] for r in ranked[:5])
        overall = statistics.mean(r["breakdown"]["matchups"] for r in ranked)
        self.assertGreater(top5, overall + 1)

    def test_full_draft_is_fast_and_sane(self):
        d = sg.Draft.from_payload({
            "allies": [{"champion": c} for c in ("Garen", "Lee Sin", "Jinx", "Thresh")],
            "enemies": [{"champion": c} for c in ("Darius", "Vi", "Yasuo", "Caitlyn", "Lux")],
            "bans": ["Zed", "Ahri"],
        })
        start = time.perf_counter()
        r = sg.analyze(d)
        self.assertLess(time.perf_counter() - start, 1.0)
        self.assertEqual(r["open_roles"], ["Mid"])
        self.assertTrue(r["suggestions"])
        self.assertTrue(all(s["role"] == "Mid" for s in r["suggestions"]))
        self.assertTrue(sg.OUTLOOK_MIN <= r["outlook"]["win_chance"] <= sg.OUTLOOK_MAX)
        self.assertFalse({s["champion"] for s in r["suggestions"]} & d.taken)


if __name__ == "__main__":
    unittest.main()
