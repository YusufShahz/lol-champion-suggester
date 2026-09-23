"""Suggestion engine and data-layer lookups on a small synthetic dataset."""

import unittest
from unittest import mock

import champion_data as cd
import suggester as sg

AVG = 51.7  # bracket average win rate, as in Emerald+ data


def lane(games, wr=AVG, pick_rate=10.0, pct=100.0, tier="A"):
    return {"games": games, "win_rate": wr, "pick_rate": pick_rate, "ban_rate": 1.0,
            "pct_lane": pct, "tier_letter": tier, "rank": 1}


def meta(damage, attack, durability=1, cc=1, roles=()):
    return {"damage_type": damage, "attack_type": attack, "roles": list(roles),
            "playstyle": {"durability": durability, "crowdControl": cc, "mobility": 2, "damage": 2, "utility": 1}}


def make_world():
    lanes = {
        "Brute": {"top": lane(50000, AVG + 2)},
        "Counter": {"top": lane(50000)},
        "Victim": {"top": lane(50000)},
        "Target": {"top": lane(50000)},
        "Oddball": {"top": lane(2000, AVG + 3.3, pick_rate=0.3)},
        "Flex": {"top": lane(20000, pick_rate=4, pct=50), "middle": lane(20000, pick_rate=4, pct=50)},
        "Wall": {"top": lane(30000, pick_rate=6, pct=60), "support": lane(20000, pick_rate=4, pct=40)},
        "Hunter": {"jungle": lane(60000)},
        "Mage": {"middle": lane(60000, AVG + 1)},
        "Blade": {"middle": lane(60000, AVG + 1)},
        "Archer": {"bottom": lane(80000)},
        "Gunner": {"bottom": lane(60000)},
        "Warden": {"support": lane(60000)},
    }
    cdragon = {
        "Brute": meta("kPhysical", "melee", 2, 1, ["fighter"]),
        "Counter": meta("kPhysical", "melee", 2, 1, ["fighter"]),
        "Victim": meta("kPhysical", "melee", 2, 1, ["fighter"]),
        "Target": meta("kPhysical", "melee", 2, 1, ["fighter"]),
        "Oddball": meta("kPhysical", "melee", 2, 1, ["fighter"]),
        "Flex": meta("kMixed", "melee", 2, 2, ["fighter"]),
        "Wall": meta("kMagic", "melee", 3, 2, ["tank"]),
        "Hunter": meta("kPhysical", "melee", 2, 2, ["fighter"]),
        "Mage": meta("kMagic", "ranged", 1, 3, ["mage"]),
        "Blade": meta("kPhysical", "melee", 1, 1, ["assassin"]),
        "Archer": meta("kPhysical", "ranged", 1, 1, ["marksman"]),
        "Gunner": meta("kPhysical", "ranged", 1, 1, ["marksman"]),
        "Warden": meta("kMagic", "melee", 2, 3, ["support"]),
    }
    matchups = {}

    def entry(name, where):
        return matchups.setdefault(name, {}).setdefault(where, {"vs": {}, "with": {}})

    def vs(a, a_lane, b, b_lane, wr, d2, games, both=True):
        entry(a, a_lane)["vs"].setdefault(b_lane, {})[b] = [wr, d2, games]
        if both:
            entry(b, b_lane)["vs"].setdefault(a_lane, {})[a] = [2 * AVG - wr, -d2, games]

    vs("Counter", "top", "Target", "top", 57.0, 5.0, 20000)
    vs("Victim", "top", "Target", "top", 47.0, -5.0, 20000)
    vs("Archer", "bottom", "Gunner", "bottom", 53.0, 3.0, 8000, both=False)
    entry("Archer", "bottom")["with"]["support"] = {"Warden": [56.0, 3.0, 20000]}

    return {
        "champions": sorted(lanes),
        "champ_stats": {name: {"lanes": l} for name, l in lanes.items()},
        "stats_meta": {"lane_avg_wr": {l: AVG for l in cd.LANES}},
        "matchups_meta": {},
        "_matchups": matchups,
        "cdragon_details": cdragon,
        "ddragon_details": {},
        "_roles_fallback": {"Newbie": ["Mid"]},
        "_lane_avg": {l: AVG for l in cd.LANES},
        "_attr_cache": {},
    }


class FakeWorld(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.multiple(cd, **make_world())
        patcher.start()
        self.addCleanup(patcher.stop)

    def score(self, champ, lane_, **draft):
        return sg.score(sg.Draft(**draft), champ, lane_)


class DataLayerTest(FakeWorld):
    def test_reverse_matchup_uses_bracket_average(self):
        # Only Archer's table has this pair; Gunner's side is derived from it
        self.assertEqual(cd.matchup("Archer", "bottom", "Gunner", "bottom"), (53.0, 3.0, 8000))
        self.assertEqual(cd.matchup("Gunner", "bottom", "Archer", "bottom"), (round(2 * AVG - 53.0, 2), -3.0, 8000))
        self.assertIsNone(cd.matchup("Mage", "middle", "Blade", "middle"))

    def test_synergy_is_read_from_either_table(self):
        self.assertEqual(cd.synergy("Warden", "support", "Archer", "bottom"), (56.0, 3.0, 20000))

    def test_playable_and_main_lanes(self):
        self.assertEqual(cd.playable_lanes("Flex"), ["top", "middle"])
        self.assertEqual(cd.playable_lanes("Wall"), ["top", "support"])
        self.assertEqual(cd.main_lane("Wall"), "top")
        self.assertEqual(cd.roles_of("Archer"), ["ADC"])

    def test_lane_distribution_falls_back_to_role_list(self):
        self.assertAlmostEqual(cd.lane_distribution("Archer")["bottom"], 1.0)
        self.assertAlmostEqual(cd.lane_distribution("Newbie")["middle"], 1.0)
        spread = cd.lane_distribution("Unknown")
        self.assertAlmostEqual(sum(spread.values()), 1.0)

    def test_damage_type_and_frontline(self):
        self.assertEqual(cd.damage_type("Mage"), "AP")
        self.assertEqual(cd.damage_type("Archer"), "AD")
        self.assertEqual(cd.damage_type("Flex"), "Mixed")
        self.assertTrue(cd.is_frontline("Wall"))
        self.assertFalse(cd.is_frontline("Archer"))


class RoleInferenceTest(FakeWorld):
    def test_single_lane_champions(self):
        roles = sg.infer_roles(["Archer", "Warden"])
        self.assertEqual(roles.assignment, {"Archer": "bottom", "Warden": "support"})

    def test_flex_pick_takes_the_lane_left_over(self):
        roles = sg.infer_roles(["Flex", "Mage"])
        self.assertEqual(roles.assignment, {"Flex": "top", "Mage": "middle"})
        self.assertGreater(roles.probability("Flex", "top"), 0.9)

    def test_pinned_lanes_are_respected(self):
        roles = sg.infer_roles(["Flex", "Mage"], pinned={"Mage": "top"})
        self.assertEqual(roles.assignment, {"Flex": "middle", "Mage": "top"})
        self.assertAlmostEqual(roles.probability("Mage", "top"), 1.0)

    def test_conflicting_pins_keep_the_first(self):
        roles = sg.infer_roles(["Archer", "Gunner"], pinned={"Archer": "bottom", "Gunner": "bottom"})
        self.assertEqual(roles.pinned, {"Archer": "bottom"})
        self.assertNotEqual(roles.assignment["Gunner"], "bottom")

    def test_blocked_lanes_are_skipped(self):
        self.assertEqual(sg.infer_roles(["Flex"], blocked=("top",)).assignment, {"Flex": "middle"})

    def test_marginals_are_distributions(self):
        roles = sg.infer_roles(["Flex", "Wall", "Mage", "Archer"])
        for name in roles.champions:
            self.assertAlmostEqual(sum(roles.marginals[name].values()), 1.0)
        for l in cd.LANES:
            self.assertLessEqual(roles.lane_filled(l), 1.0)

    def test_duplicates_and_blanks_ignored(self):
        self.assertEqual(sg.infer_roles(["Archer", "", "Archer"]).champions, ["Archer"])
        self.assertEqual(sg.infer_roles([]).champions, [])


class DraftTest(FakeWorld):
    def test_cleans_names_lanes_and_duplicates(self):
        d = sg.Draft(allies=[("Archer", "ADC"), ("Archer", None), ("Nobody", None), ("Warden", "support")])
        self.assertEqual(d.allies, [("Archer", "bottom"), ("Warden", "support")])

    def test_my_pick_is_not_an_ally(self):
        d = sg.Draft(my_pick="Archer", allies=[("Archer", None), ("Warden", None)])
        self.assertEqual(d.ally_names, ["Warden"])

    def test_team_sizes_are_capped(self):
        names = [(n, None) for n in make_world()["champions"]]
        d = sg.Draft(allies=names, enemies=names)
        self.assertEqual(len(d.ally_names), 4)
        self.assertEqual(len(d.enemy_names), 5)

    def test_lane_accepts_role_or_lane_names(self):
        self.assertEqual(sg.Draft(my_lane="Mid").my_lane, "middle")
        self.assertEqual(sg.Draft(my_lane="support").my_lane, "support")
        self.assertIsNone(sg.Draft(my_lane="Carry").my_lane)

    def test_comfort_is_clamped(self):
        self.assertEqual(sg.Draft(comfort=99).comfort, sg.MAX_COMFORT)
        self.assertEqual(sg.Draft(comfort=-3).comfort, 0.0)
        self.assertEqual(sg.Draft(comfort="lots").comfort, sg.DEFAULT_COMFORT)

    def test_pool_only_needs_a_pool(self):
        self.assertFalse(sg.Draft(pool_only=True).pool_only)
        self.assertTrue(sg.Draft(pool_only=True, pool=["Mage"]).pool_only)

    def test_payload_with_legacy_field_names(self):
        d = sg.Draft.from_payload({"assigned_role": "Mid", "ally_picks": ["Archer"], "enemy_picks": ["Target"]})
        self.assertEqual(d.my_lane, "middle")
        self.assertEqual(d.allies, [("Archer", None)])
        self.assertEqual(d.enemies, [("Target", None)])

    def test_malformed_payload_does_not_crash(self):
        d = sg.Draft.from_payload({"my_role": 3, "my_pick": ["Mage"], "allies": "Archer",
                                   "enemies": [1, None, {"champion": 5}, {"champion": "Target", "role": 7}],
                                   "bans": "Brute", "pool": [3, "Mage"], "comfort": None, "available": "all"})
        self.assertIsNone(d.my_lane)
        self.assertEqual(d.my_pick, "")
        self.assertEqual(d.ally_names, [])
        self.assertEqual(d.enemies, [("Target", None)])
        self.assertEqual(d.bans, set())
        self.assertEqual(d.pool, {"Mage"})
        self.assertEqual(d.comfort, sg.DEFAULT_COMFORT)
        self.assertIsNone(d.available)


class ScoreTest(FakeWorld):
    def test_estimate_is_fifty_plus_breakdown(self):
        r = self.score("Mage", "middle", allies=[("Counter", None), ("Hunter", None), ("Archer", None)],
                       enemies=[("Target", "Top")], pool=["Mage"])
        self.assertAlmostEqual(r["estimate"], 50 + sum(r["breakdown"].values()), delta=0.1)

    def test_counter_scores_above_countered(self):
        enemy = {"enemies": [("Target", "Top")], "my_lane": "Top"}
        good, bad = self.score("Counter", "top", **enemy), self.score("Victim", "top", **enemy)
        self.assertGreater(good["breakdown"]["matchups"], 4)
        self.assertLess(bad["breakdown"]["matchups"], -4)
        self.assertIn("Strong vs Target", [x["text"] for x in good["reasons"]])
        self.assertIn("Weak vs Target", [x["text"] for x in bad["reasons"]])
        self.assertTrue(good["lane_opponent_known"])

    def test_blind_pick_risk_while_lane_opponent_unknown(self):
        blind = self.score("Victim", "top", my_lane="Top")
        self.assertLess(blind["breakdown"]["blind_risk"], 0)
        self.assertEqual([c["champion"] for c in blind["counters"]], ["Target"])
        self.assertIn("Counter-pick risk: Target", [x["text"] for x in blind["reasons"]])
        self.assertEqual(self.score("Counter", "top", my_lane="Top")["breakdown"]["blind_risk"], 0)

    def test_no_blind_risk_once_counter_is_gone_or_laner_known(self):
        self.assertEqual(self.score("Victim", "top", my_lane="Top", bans=["Target"])["breakdown"]["blind_risk"], 0)
        known = self.score("Victim", "top", my_lane="Top", enemies=[("Wall", "Top")])
        self.assertEqual(known["breakdown"]["blind_risk"], 0)

    def test_synergy_with_allies(self):
        archer = self.score("Archer", "bottom", allies=[("Warden", None)])
        gunner = self.score("Gunner", "bottom", allies=[("Warden", None)])
        self.assertGreater(archer["breakdown"]["synergy"], 2)
        self.assertEqual(gunner["breakdown"]["synergy"], 0)
        self.assertIn("Pairs well with Warden", [x["text"] for x in archer["reasons"]])

    def test_comfort_bonus_only_for_pool(self):
        base = self.score("Victim", "top", my_lane="Top")
        pooled = self.score("Victim", "top", my_lane="Top", pool=["Victim"], comfort=2.0)
        self.assertAlmostEqual(pooled["estimate"] - base["estimate"], 2.0, places=1)
        self.assertTrue(pooled["in_pool"])
        self.assertIn("In your champion pool", [x["text"] for x in pooled["reasons"]])

    def test_needs_enough_games(self):
        self.assertIsNone(sg.score(sg.Draft(), "Oddball", "top", min_games=5000))
        self.assertIsNone(sg.score(sg.Draft(), "Archer", "top"))

    def test_off_role_flag(self):
        r = self.score("Wall", "support")
        self.assertTrue(r["off_role"])
        self.assertEqual(r["main_role"], "Top")


class CompositionTest(FakeWorld):
    ALLIES = [("Counter", None), ("Hunter", None), ("Archer", None)]

    def test_magic_damage_and_cc_for_physical_team(self):
        d = sg.Draft(my_lane="Mid", allies=self.ALLIES)
        mage, mage_notes = sg.composition(d, "Mage", "middle", d.ally_roles("middle"))
        blade, _ = sg.composition(d, "Blade", "middle", d.ally_roles("middle"))
        self.assertGreater(mage, blade)
        texts = [n["text"] for n in mage_notes]
        self.assertIn("Adds magic damage to a mostly physical team", texts)
        self.assertIn("Brings crowd control your team lacks", texts)

    def test_composition_decides_between_equal_champions(self):
        ranked = sg.rank_candidates(sg.Draft(my_lane="Mid", allies=self.ALLIES))
        names = [r["champion"] for r in ranked]
        self.assertLess(names.index("Mage"), names.index("Blade"))

    def test_frontline_for_team_without_one(self):
        d = sg.Draft(my_lane="Top", allies=[("Hunter", None), ("Archer", None)])
        points, notes = sg.composition(d, "Wall", "top", d.ally_roles("top"))
        self.assertGreater(points, 0)
        self.assertIn("Adds the frontline your team lacks", [n["text"] for n in notes])

    def test_needs_two_allies(self):
        d = sg.Draft(my_lane="Mid", allies=[("Archer", None)])
        self.assertEqual(sg.composition(d, "Mage", "middle", d.ally_roles("middle")), (0.0, []))


class RankingTest(FakeWorld):
    def test_blind_pick_prefers_meta_strength(self):
        ranked = sg.rank_candidates(sg.Draft(my_lane="Top"))
        self.assertEqual(ranked[0]["champion"], "Brute")
        self.assertTrue(all(r["lane"] == "top" for r in ranked))
        self.assertEqual([r["rank"] for r in ranked], list(range(1, len(ranked) + 1)))
        estimates = [r["estimate"] for r in ranked]
        self.assertEqual(estimates, sorted(estimates, reverse=True))

    def test_taken_and_unavailable_champions_excluded(self):
        names = {r["champion"] for r in sg.rank_candidates(
            sg.Draft(my_lane="Top", bans=["Brute"], enemies=[("Counter", None)]))}
        self.assertFalse(names & {"Brute", "Counter"})
        only = sg.rank_candidates(sg.Draft(my_lane="Top", available=["Victim", "Mage"]))
        self.assertEqual([r["champion"] for r in only], ["Victim"])

    def test_pool_only(self):
        ranked = sg.rank_candidates(sg.Draft(my_lane="Top", pool=["Victim", "Mage"], pool_only=True))
        self.assertEqual([r["champion"] for r in ranked], ["Victim"])

    def test_niche_picks_hidden_unless_asked_or_in_pool(self):
        def names(**kw):
            return {r["champion"] for r in sg.rank_candidates(sg.Draft(my_lane="Top", **kw))}
        self.assertNotIn("Oddball", names())
        self.assertIn("Oddball", names(include_niche=True))
        self.assertIn("Oddball", names(pool=["Oddball"]))

    def test_without_a_role_only_open_lanes(self):
        d = sg.Draft(allies=[("Counter", "Top"), ("Hunter", "Jungle"), ("Archer", "ADC"), ("Warden", "Support")])
        self.assertEqual(d.open_lanes(), ["middle"])
        self.assertTrue(all(r["lane"] == "middle" for r in sg.rank_candidates(d)))

    def test_flex_champion_scored_in_its_best_open_lane(self):
        ranked = sg.rank_candidates(sg.Draft(allies=[("Mage", "Mid")]))
        flex = next(r for r in ranked if r["champion"] == "Flex")
        self.assertEqual(flex["lane"], "top")


class BanTest(FakeWorld):
    def test_bans_target_my_lane_while_opponent_unknown(self):
        d = sg.Draft(my_lane="Top")
        self.assertEqual(sg.ban_lanes(d), ["top"])
        bans = sg.suggest_bans(d)
        self.assertEqual(bans[0]["champion"], "Brute")
        self.assertTrue(all(b["lane"] == "top" for b in bans))

    def test_bans_prioritise_pool_counters(self):
        bans = sg.suggest_bans(sg.Draft(my_lane="Top", pool=["Victim"]))
        self.assertEqual(bans[0]["champion"], "Target")
        self.assertEqual(bans[0]["beats_pool"][0]["champion"], "Victim")
        self.assertIn("Beats your Victim", bans[0]["reasons"])
        self.assertNotIn("Victim", [b["champion"] for b in bans])

    def test_bans_skip_filled_lanes_and_taken_champions(self):
        d = sg.Draft(my_lane="Top", enemies=[("Target", "Top")], bans=["Mage"], my_pick="Archer")
        self.assertNotIn("top", sg.ban_lanes(d))
        names = [b["champion"] for b in sg.suggest_bans(d, count=20)]
        self.assertFalse({"Target", "Mage", "Archer"} & set(names))
        self.assertEqual(len(names), len(set(names)))


class OutlookAndTeamTest(FakeWorld):
    def test_outlook_needs_both_teams(self):
        self.assertIsNone(sg.draft_outlook(sg.Draft(allies=[("Mage", None)])))
        self.assertIsNone(sg.draft_outlook(sg.Draft(enemies=[("Mage", None)])))

    def test_outlook_is_mirror_symmetric(self):
        a = [("Counter", "Top"), ("Mage", "Mid")]
        b = [("Target", "Top"), ("Blade", "Mid")]
        ours = sg.draft_outlook(sg.Draft(allies=a, enemies=b))
        theirs = sg.draft_outlook(sg.Draft(allies=b, enemies=a))
        self.assertGreater(ours["win_chance"], 54)
        self.assertAlmostEqual(ours["win_chance"] + theirs["win_chance"], 100.0, delta=0.11)

    def test_outlook_is_clamped(self):
        cd._matchups["Counter"]["top"]["vs"]["top"]["Target"] = [99.0, 60.0, 10 ** 7]
        out = sg.draft_outlook(sg.Draft(allies=[("Counter", "Top")], enemies=[("Target", "Top")]))
        self.assertEqual(out["win_chance"], sg.OUTLOOK_MAX)

    def test_team_summary(self):
        ally = sg.team_summary(sg.infer_roles(["Counter", "Hunter", "Archer"]), "ally")
        self.assertAlmostEqual(sum(ally["damage"].values()), 1.0, delta=0.02)
        self.assertGreater(ally["damage"]["physical"], 0.8)
        self.assertEqual(ally["frontline"], 0)
        self.assertEqual((ally["melee"], ally["ranged"]), (2, 1))
        self.assertEqual(ally["notes"], ["Mostly physical damage - armor stacking hurts", "No frontline",
                                         "Little crowd control"])
        enemy = sg.team_summary(sg.infer_roles(["Counter", "Hunter", "Archer"]), "enemy")
        self.assertIn("No frontline - they are vulnerable to dive", enemy["notes"])
        self.assertEqual(sg.team_summary(sg.infer_roles([]), "ally")["picks"], [])


class AnalyzeTest(FakeWorld):
    def test_result_shape(self):
        r = sg.analyze(sg.Draft(my_lane="Top", allies=[("Mage", None)], enemies=[("Target", None)]), count=3)
        self.assertEqual(set(r), {"lane", "role", "open_roles", "suggestions", "eligible", "my_pick", "bans",
                                  "ban_roles", "teams", "outlook", "has_matchups"})
        self.assertLessEqual(len(r["suggestions"]), 3)
        self.assertEqual(r["role"], "Top")
        self.assertIsNotNone(r["outlook"])

    def test_my_pick_evaluated_even_when_off_meta(self):
        r = sg.analyze(sg.Draft(my_lane="Top", my_pick="Oddball"))
        self.assertNotIn("Oddball", [s["champion"] for s in r["suggestions"]])
        self.assertEqual(r["my_pick"]["champion"], "Oddball")
        self.assertGreaterEqual(r["my_pick"]["rank"], 1)
        me = [p for p in r["teams"]["ally"]["picks"] if p["is_me"]]
        self.assertEqual([p["champion"] for p in me], ["Oddball"])


if __name__ == "__main__":
    unittest.main()
