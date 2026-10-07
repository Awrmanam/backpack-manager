import json
import tempfile
import unittest
from pathlib import Path

from backpack_manager.backpack import Snapshot, auto_download_direction, counters_for, discover
from backpack_manager.db import Database


class BackPackTests(unittest.TestCase):
    def test_download_direction_for_iran_server(self):
        s = Snapshot("x","server","tcp",bytes_in=1200,bytes_out=500,connected=True,taken=None)
        self.assertEqual(counters_for(s,"auto"),(1200,500))
        self.assertEqual(auto_download_direction("server"),"in")

    def test_client_direction_is_opposite(self):
        s = Snapshot("x","client","tcp",bytes_in=500,bytes_out=1200,connected=True,taken=None)
        self.assertEqual(counters_for(s,"auto"),(1200,500))

    def test_discovery_reads_existing_and_new_tunnels(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            (p/"old.toml").write_text('[server]\nbind_addr="0.0.0.0:443"\ntransport="tcp"\nports=["2000-2009","3000"]\n')
            self.assertEqual([x.name for x in discover(td)],["old"])
            (p/"new.toml").write_text('[server]\nbind_addr="0.0.0.0:8443"\ntransport="tcp"\nports=["4000"]\n')
            self.assertEqual([x.name for x in discover(td)],["new","old"])

    def test_all_ports_share_one_tunnel_counter_not_multiplied(self):
        with tempfile.TemporaryDirectory() as td:
            db=Database(str(Path(td)/"db.sqlite"))
            class T: pass
            t=T(); t.name="customer"; t.role="server"; t.transport="tcp"; t.ports=["1000","1001","1002-1010"]; t.config_path="x"; t.metrics_path="m"
            db.sync_discovery([t])
            # First observation establishes the baseline.
            self.assertEqual(db.update_counter("customer",1000),0)
            # The next 500 bytes are counted ONCE for the whole tunnel, even
            # though it contains many forwarded ports.
            self.assertEqual(db.update_counter("customer",1500),500)
            self.assertEqual(db.get("customer")["usage_bytes"],500)

    def test_counter_reset_preserves_accumulated_usage(self):
        with tempfile.TemporaryDirectory() as td:
            db=Database(str(Path(td)/"db.sqlite"))
            class T: pass
            t=T(); t.name="x"; t.role="server"; t.transport="tcp"; t.ports=[]; t.config_path="x"; t.metrics_path="m"
            db.sync_discovery([t]); db.update_counter("x",1000); db.update_counter("x",1300)
            self.assertEqual(db.update_counter("x",50),350)

if __name__ == "__main__": unittest.main()
