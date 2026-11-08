from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from fetchdeck.dashboard_server import DashboardServer
from fetchdeck.statistics import StatisticsStore


class StatisticsStoreTests(unittest.TestCase):
    def test_restored_bytes_are_baselined_and_new_transfer_is_counted_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "activity.json"
            store = StatisticsStore(path)
            restored = {"gid": "old", "completedLength": "800", "uploadLength": "0", "status": "active"}
            store.observe([restored])
            store.observe([{**restored, "completedLength": "900"}])
            store.observe([{**restored, "completedLength": "900"}])
            fresh = {"gid": "new", "completedLength": "100", "uploadLength": "0", "status": "active"}
            store.observe([fresh], fresh_gids={"new"})
            data = json.loads(path.read_text(encoding="utf-8"))
            today = next(iter(data["days"].values()))
            self.assertEqual(today["download"], 200)

    def test_snapshot_contains_only_aggregated_statistics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StatisticsStore(Path(directory) / "activity.json")
            snapshot = store.snapshot(
                engine_status="running",
                engine_version="aria2 1.37.0",
                tasks=[{"gid": "secret-gid", "status": "active", "completedLength": "5", "downloadSpeed": "7", "files": [{"path": "C:/private/file", "uris": [{"uri": "https://private.invalid/key"}]}]}],
            )
            serialized = json.dumps(snapshot)
            for private_value in ("secret-gid", "private", "https://", "path"):
                self.assertNotIn(private_value, serialized)


class DashboardServerTests(unittest.TestCase):
    def test_serves_stats_same_origin_and_rejects_wrong_host_origin_and_method(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("dashboard", encoding="utf-8")
            server = DashboardServer(root, lambda: {"version": 1, "counts": {"active": 0}})
            address = server.start()
            try:
                with urlopen(address) as response:
                    self.assertEqual(response.read(), b"dashboard")
                with urlopen(address + "api/v1/stats") as response:
                    self.assertEqual(json.load(response), {"version": 1, "counts": {"active": 0}})
                with self.assertRaises(HTTPError) as bad_origin:
                    urlopen(Request(address + "api/v1/stats", headers={"Origin": "https://attacker.invalid"}))
                self.assertEqual(bad_origin.exception.code, 403)
                with self.assertRaises(HTTPError) as bad_host:
                    urlopen(Request(address + "api/v1/stats", headers={"Host": "localhost"}))
                self.assertEqual(bad_host.exception.code, 400)
                with self.assertRaises(HTTPError) as wrong_method:
                    urlopen(Request(address + "api/v1/stats", method="POST"))
                self.assertEqual(wrong_method.exception.code, 405)
            finally:
                server.close()


if __name__ == "__main__":
    unittest.main()
