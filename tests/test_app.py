"""Flask routes, live client state and the SSE poller, with the League client mocked out."""

import json
import re
import socket
import unittest
from unittest import mock

import app as appmod
import champion_data as cd

IDS = {103: "Ahri", 157: "Yasuo", 238: "Zed", 11: "Master Yi", 64: "Lee Sin"}
needs_data = unittest.skipUnless(cd.champ_stats, "run py data/update_data.py first")


def parsed_session():
    return {
        "me": {"cell_id": 2, "champion_id": 103, "state": "hovering", "role": "Mid"},
        "allies": [{"cell_id": 0, "champion_id": 0, "state": "", "role": "Top"},
                   {"cell_id": 1, "champion_id": 64, "state": "locked", "role": "Jungle"}],
        "enemies": [{"cell_id": 5, "champion_id": 157, "state": "locked"},
                    {"cell_id": 6, "champion_id": 0, "state": ""}],
        "bans": {"ally": [238], "enemy": [11]},
        "phase": "BAN_PICK", "time_left_ms": 25000, "total_time_ms": 30000,
        "action": {"type": "pick", "is_mine": True, "is_ally": True},
        "game_id": 99,
    }


class RoutesTest(unittest.TestCase):
    def setUp(self):
        self.client = appmod.app.test_client()

    def suggest(self, body):
        resp = self.client.post("/suggest", json=body)
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()

    def test_index_inlines_bootstrap(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        m = re.search(r'<script id="bootstrap" type="application/json">(.*?)</script>', resp.get_data(as_text=True), re.S)
        self.assertIsNotNone(m)
        self.assertEqual(len(json.loads(m.group(1))["champions"]), len(cd.champions))

    def test_bootstrap(self):
        data = self.client.get("/api/bootstrap").get_json()
        self.assertEqual(data["roles"], ["Top", "Jungle", "Mid", "ADC", "Support"])
        self.assertEqual(set(data["defaults"]), {"count", "max_count", "comfort", "max_comfort", "niche_pick_rate"})
        for c in data["champions"]:
            self.assertLessEqual({"name", "icon", "roles", "lanes", "damage", "attack_type", "classes"}, set(c))

    def test_meta(self):
        data = self.client.get("/api/meta").get_json()
        self.assertLessEqual({"patch", "tier_bracket", "has_stats", "has_matchups", "ddragon_version"}, set(data))

    def test_suggest_rejects_non_objects(self):
        self.assertEqual(self.client.post("/suggest").status_code, 400)
        self.assertEqual(self.client.post("/suggest", data="nope", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post("/suggest", json=[1, 2]).status_code, 400)

    @needs_data
    def test_suggest_count_is_bounded(self):
        def count(value):
            return len(self.suggest({"count": value, "include_niche": True})["suggestions"])
        self.assertEqual(count(3), 3)
        self.assertEqual(count("lots"), appmod.DEFAULT_SUGGESTIONS)
        self.assertEqual(count(10 ** 4), appmod.MAX_SUGGESTIONS)
        self.assertEqual(count(0), 1)

    @needs_data
    def test_suggest_full_draft(self):
        r = self.suggest({
            "my_role": "Mid", "my_pick": "Ahri", "count": 5,
            "allies": [{"champion": "Garen", "role": "Top"}, {"champion": "Lee Sin"}, {"champion": "Not A Champion"}],
            "enemies": [{"champion": "Yasuo"}, {"champion": "Vi"}],
            "bans": ["Zed", "Syndra"],
        })
        names = {s["champion"] for s in r["suggestions"]}
        self.assertEqual(len(r["suggestions"]), 5)
        self.assertFalse(names & {"Zed", "Syndra", "Garen", "Lee Sin", "Yasuo", "Vi"})
        self.assertTrue(all(s["role"] == "Mid" for s in r["suggestions"]))
        self.assertEqual(r["my_pick"]["champion"], "Ahri")
        self.assertEqual([p["champion"] for p in r["teams"]["ally"]["picks"]], ["Garen", "Lee Sin", "Ahri"])
        self.assertEqual(len(r["teams"]["enemy"]["picks"]), 2)
        self.assertIsNotNone(r["outlook"])
        self.assertEqual(r["patch"], cd.stats_meta.get("patch", ""))


class LiveStateTest(unittest.TestCase):
    def setUp(self):
        self.client = appmod.app.test_client()
        self.patch(appmod.ddragon, get_champion_id_to_name=IDS)

    def patch(self, target=appmod.lcu, **methods):
        for name, value in methods.items():
            p = mock.patch.object(target, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def test_offline(self):
        self.patch(is_running=False)
        self.assertEqual(self.client.get("/lcu/status").get_json(), {"type": "offline"})

    def test_connected_outside_champ_select(self):
        self.patch(is_running=True, gameflow_phase="Lobby", summoner={"name": "Tester#EUW"})
        self.assertEqual(appmod.read_live_state(), {"type": "connected", "gameflow": "Lobby", "summoner": "Tester#EUW"})

    def test_champ_select(self):
        self.patch(is_running=True, gameflow_phase="ChampSelect", summoner={"name": "Tester#EUW"},
                   champ_select=parsed_session(), pickable_ids=[103, 64, 999])
        s = appmod.read_live_state()
        self.assertEqual((s["type"], s["phase"], s["my_role"]), ("champ_select", "BAN_PICK", "Mid"))
        self.assertEqual(s["me"], {"champion": "Ahri", "state": "hovering"})
        self.assertEqual(s["allies"][1], {"champion": "Lee Sin", "role": "Jungle", "state": "locked"})
        self.assertEqual([e["champion"] for e in s["enemies"]], ["Yasuo", ""])
        self.assertEqual(s["bans"], {"ally": ["Zed"], "enemy": ["Master Yi"]})
        self.assertEqual(s["pickable"], ["Ahri", "Lee Sin"])
        self.assertEqual((s["timer"]["left_ms"], s["timer"]["total_ms"]), (25000, 30000))

    def test_mastery(self):
        self.patch(mastery=None)
        self.assertEqual(self.client.get("/lcu/mastery").get_json(), {"available": False, "champions": []})

    def test_mastery_names_and_limit(self):
        self.patch(mastery=[{"champion_id": 999, "level": 7, "points": 5000},
                            {"champion_id": 103, "level": 7, "points": 900},
                            {"champion_id": 64, "level": 5, "points": 100}])
        self.assertEqual(self.client.get("/lcu/mastery?limit=1").get_json(),
                         {"available": True, "champions": [{"champion": "Ahri", "level": 7, "points": 900}]})

    def test_owned(self):
        self.patch(owned_ids=[103, 999])
        self.assertEqual(self.client.get("/lcu/owned").get_json(), {"available": True, "champions": ["Ahri"]})

    def test_owned_unavailable(self):
        self.patch(owned_ids=None)
        self.assertEqual(self.client.get("/lcu/owned").get_json(), {"available": False, "champions": []})


class LivePollerTest(unittest.TestCase):
    def test_timer_only_changes_do_not_wake_listeners(self):
        p = appmod.LivePoller(read=dict)
        p.publish({"type": "champ_select", "phase": "BAN_PICK", "timer": {"left_ms": 5}})
        version, state = p.wait(0, timeout=0.1)
        self.assertEqual(version, 1)
        p.publish({"type": "champ_select", "phase": "BAN_PICK", "timer": {"left_ms": 4}})
        self.assertEqual(p.wait(version, timeout=0.05), (version, None))
        p.publish({"type": "champ_select", "phase": "FINALIZATION", "timer": {"left_ms": 4}})
        version, state = p.wait(version, timeout=0.1)
        self.assertEqual((version, state["phase"]), (2, "FINALIZATION"))

    def test_subscribe_starts_polling(self):
        p = appmod.LivePoller(read=lambda: {"type": "offline"})
        p.subscribe()
        try:
            self.assertEqual(p.wait(0, timeout=3)[1], {"type": "offline"})
        finally:
            p.unsubscribe()

    def test_poll_errors_are_published(self):
        def boom():
            raise RuntimeError("client exploded")

        p = appmod.LivePoller(read=boom)
        with mock.patch.object(appmod.app.logger, "exception"):
            p.subscribe()
            try:
                state = p.wait(0, timeout=3)[1]
            finally:
                p.unsubscribe()
        self.assertEqual(state, {"type": "error", "message": "client exploded"})

    def test_stream_sends_state_and_unsubscribes_on_close(self):
        poller = appmod.LivePoller(read=lambda: {"type": "offline"})
        with mock.patch.object(appmod, "live", poller), mock.patch.object(appmod, "HEARTBEAT", 0.2):
            resp = appmod.app.test_client().get("/lcu/stream", buffered=False)
            self.assertEqual(resp.mimetype, "text/event-stream")
            chunks = iter(resp.response)
            self.assertEqual(next(chunks), b"retry: 3000\n\n")
            chunk = next(c for c, _ in zip(chunks, range(20)) if c.startswith(b"data:"))
            self.assertEqual(json.loads(chunk[len(b"data:"):]), {"type": "offline"})
            resp.close()
        self.assertEqual(poller._listeners, 0)


class PortCheckTest(unittest.TestCase):
    def test_detects_listening_socket(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            s.listen(8)
            port = s.getsockname()[1]
            self.assertTrue(appmod.port_in_use("127.0.0.1", port))
            self.assertTrue(appmod.port_in_use("0.0.0.0", port))
        self.assertFalse(appmod.port_in_use("127.0.0.1", port))


if __name__ == "__main__":
    unittest.main()
