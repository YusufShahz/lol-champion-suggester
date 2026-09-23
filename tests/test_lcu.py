"""League client integration: session parsing and the HTTP client's retry / credential logic."""

import unittest
from unittest import mock

import requests

import lcu_api
from lcu_api import LCUClient, parse_session


def pick(cell, champion=0, completed=False, in_progress=False, ally=True):
    return {"actorCellId": cell, "championId": champion, "completed": completed,
            "isInProgress": in_progress, "isAllyAction": ally, "type": "pick"}


def ban(cell, champion, completed=True, ally=True):
    return {"actorCellId": cell, "championId": champion, "completed": completed,
            "isInProgress": False, "isAllyAction": ally, "type": "ban"}


def sample_session():
    """My turn to pick (hovering Ahri) with a mix of locked, hovered and declared picks."""
    return {
        "localPlayerCellId": 2,
        "gameId": 99,
        "myTeam": [
            {"cellId": 0, "championId": 0, "championPickIntent": 0, "assignedPosition": "top"},
            {"cellId": 1, "championId": 64, "championPickIntent": 0, "assignedPosition": "jungle"},
            {"cellId": 2, "championId": 103, "championPickIntent": 0, "assignedPosition": "middle"},
            {"cellId": 3, "championId": 0, "championPickIntent": 222, "assignedPosition": "bottom"},
            {"cellId": 4, "championId": 412, "championPickIntent": 0, "assignedPosition": "utility"},
        ],
        "theirTeam": [{"cellId": 5, "championId": 157}] + [{"cellId": c, "championId": 0} for c in range(6, 10)],
        "actions": [
            [ban(0, 238), ban(5, 11, ally=False), ban(1, 99, completed=False)],
            [pick(1, 64, completed=True), pick(5, 157, completed=True, ally=False)],
            [pick(2, 103, in_progress=True), pick(4, 412, completed=True)],
            [pick(0), pick(3)] + [pick(c, ally=False) for c in range(6, 10)],
        ],
        "bans": {"myTeamBans": [238, 40], "theirTeamBans": [11]},
        "timer": {"phase": "BAN_PICK", "adjustedTimeLeftInPhase": 25000, "totalTimeInPhase": 30000},
    }


class ParseSessionTest(unittest.TestCase):
    def setUp(self):
        self.s = parse_session(sample_session())

    def test_local_player(self):
        self.assertEqual(self.s["me"], {"cell_id": 2, "champion_id": 103, "state": "hovering", "role": "Mid"})

    def test_allies_with_states_and_roles(self):
        allies = [(a["champion_id"], a["state"], a["role"]) for a in self.s["allies"]]
        self.assertEqual(allies, [(0, "", "Top"), (64, "locked", "Jungle"), (222, "intent", "ADC"),
                                  (412, "locked", "Support")])

    def test_enemies(self):
        self.assertEqual([(e["champion_id"], e["state"]) for e in self.s["enemies"]],
                         [(157, "locked")] + [(0, "")] * 4)

    def test_bans_per_team_without_hovers_or_duplicates(self):
        self.assertEqual(self.s["bans"], {"ally": [238, 40], "enemy": [11]})

    def test_turn_and_timer(self):
        self.assertEqual(self.s["action"], {"type": "pick", "is_mine": True, "is_ally": True})
        self.assertEqual((self.s["phase"], self.s["time_left_ms"], self.s["total_time_ms"]), ("BAN_PICK", 25000, 30000))
        self.assertEqual(self.s["game_id"], 99)

    def test_enemy_turn(self):
        data = sample_session()
        data["actions"][2][0] = pick(2, 103, completed=True)
        data["actions"][3][2] = pick(6, 0, in_progress=True, ally=False)
        s = parse_session(data)
        self.assertEqual(s["action"], {"type": "pick", "is_mine": False, "is_ally": False})
        self.assertEqual(s["me"]["state"], "locked")

    def test_champion_without_pick_actions_counts_as_locked(self):
        data = sample_session()
        data["actions"] = []
        data["myTeam"][0]["championId"] = 55
        self.assertEqual(parse_session(data)["allies"][0]["state"], "locked")

    def test_completed_pick_recovered_when_slot_is_empty(self):
        data = sample_session()
        data["myTeam"][1]["championId"] = 0
        ally = parse_session(data)["allies"][1]
        self.assertEqual((ally["champion_id"], ally["state"]), (64, "locked"))

    def test_malformed_session(self):
        s = parse_session({"myTeam": [], "actions": [None, [None, "x"]], "timer": None, "bans": None})
        self.assertEqual(s["me"]["champion_id"], 0)
        self.assertEqual((s["allies"], s["enemies"], s["action"], s["phase"]), ([], [], None, ""))
        self.assertEqual(s["bans"], {"ally": [], "enemy": []})


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


class FakeSession:
    """Plays back a list of responses (or exceptions) and records the requested URLs."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class ClientTest(unittest.TestCase):
    def client(self, *responses, creds=("1234", "token")):
        c = LCUClient()
        c._session = FakeSession(*responses)
        patcher = mock.patch.object(lcu_api, "_find_client", return_value=creds)
        self.find = patcher.start()
        self.addCleanup(patcher.stop)
        return c

    def test_get_returns_json(self):
        c = self.client(FakeResponse(200, {"ok": 1}))
        self.assertEqual(c.get("/x"), {"ok": 1})
        self.assertEqual(c._session.urls, ["https://127.0.0.1:1234/x"])

    def test_get_rescans_after_connection_error(self):
        c = self.client(requests.ConnectionError(), FakeResponse(200, [1]))
        c.credentials()
        self.assertEqual(c.get("/x"), [1])
        self.assertEqual(self.find.call_count, 2)

    def test_get_rescans_after_auth_failure(self):
        c = self.client(FakeResponse(401), FakeResponse(200, "Lobby"))
        self.assertEqual(c.gameflow_phase(), "Lobby")

    def test_get_gives_up_after_second_failure(self):
        c = self.client(requests.ConnectionError(), requests.ConnectionError())
        self.assertIsNone(c.get("/x"))

    def test_get_without_client(self):
        c = self.client(creds=None)
        self.assertIsNone(c.get("/x"))
        self.assertFalse(c.is_running())
        self.assertEqual(c._session.urls, [])

    def test_process_scan_is_throttled(self):
        c = self.client(creds=None)
        for _ in range(5):
            c.credentials()
        self.assertEqual(self.find.call_count, 1)

    def test_summoner_name_with_tag(self):
        c = self.client(FakeResponse(200, {"gameName": "Faker", "tagLine": "KR1", "summonerId": 7, "puuid": "p"}))
        self.assertEqual(c.summoner(), {"name": "Faker#KR1", "summoner_id": 7, "puuid": "p"})
        self.assertEqual(c.summoner()["name"], "Faker#KR1")  # cached, no second request
        self.assertEqual(len(c._session.urls), 1)

    def test_owned_ids(self):
        c = self.client(FakeResponse(200, [
            {"id": 1, "ownership": {"owned": True}},
            {"id": 2, "ownership": {"owned": False, "rental": {"rented": True}}},
            {"id": 3, "ownership": {"owned": False}, "freeToPlay": True},
            {"id": 4, "ownership": {"owned": False}},
            {"id": -1, "ownership": {"owned": True}},
        ]))
        self.assertEqual(c.owned_ids(), [1, 2, 3])

    def test_mastery_sorted_by_points(self):
        c = self.client(FakeResponse(200, [
            {"championId": 1, "championLevel": 5, "championPoints": 100},
            {"championId": 2, "championLevel": 7, "championPoints": 900},
            {"championId": 0, "championLevel": 1, "championPoints": 5000},
            "junk",
        ]))
        self.assertEqual([m["champion_id"] for m in c.mastery()], [2, 1])

    def test_mastery_falls_back_to_collections_endpoint(self):
        c = self.client(FakeResponse(404), FakeResponse(200, {"gameName": "A", "summonerId": 42}),
                        FakeResponse(200, [{"championId": 9, "championLevel": 3, "championPoints": 10}]))
        self.assertEqual(c.mastery(), [{"champion_id": 9, "level": 3, "points": 10}])
        self.assertTrue(c._session.urls[-1].endswith("/lol-collections/v1/inventories/42/champion-mastery"))

    def test_pickable_ids(self):
        c = self.client(FakeResponse(200, [103, 0, 64]))
        self.assertEqual(c.pickable_ids(), [103, 64])

    def test_champ_select_outside_champ_select(self):
        c = self.client(FakeResponse(404))
        self.assertIsNone(c.champ_select())


if __name__ == "__main__":
    unittest.main()
