"""A1 Phase 4 unit tests: SpeckHSM, DeviceKeyStore, C2 replay guard.

Covers the PC integration of Speck64/96 as the R2 algorithm (hsm.py /
protocol.py / main.py) plus the P1-2 replay-window fix.

Run from the repository root::

    python tests\\test_a1_phase4.py
    python -m unittest tests.test_a1_phase4 -v
"""

import contextlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.python.common.speck import Speck6496
from src.python.server.crp_pool import CRPPoolRegistry
from src.python.server.hsm import DEVICE_KEY_BYTES, SpeckHSM, hsm_status
from src.python.server.main import DeviceKeyStore, LoopbackTransport
from src.python.server.protocol import (
    RESULT_PASS,
    RESULT_REPLAY,
    HFIDAProtocol,
    ProtocolError,
    crc16_mcrf4xx,
)
from src.python.server.template_db import TemplateDB

#: W3 demo values shared with the RTL (terminal_fsm.v DEVICE_KEY parameter
#: 96'h13121110_0b0a0908_03020100 == NSA-KAT key in wire byte order).
W3_KEY = bytes.fromhex("0001020308090a0b10111213")
W3_FIRST_C2 = bytes.fromhex("a1a2a3a4a5a6a7a8")
W3_FIRST_R2 = bytes.fromhex("7b45b0545e59aa94")


class TempDirTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)


class TestSpeckHSM(TempDirTest):
    def test_golden_vector_matches_rtl(self) -> None:
        """The HSM path reproduces the tb_terminal_fsm golden R2."""
        hsm = SpeckHSM(keys={1: W3_KEY})
        self.assertEqual(hsm.respond(W3_FIRST_C2, terminal_id=1), W3_FIRST_R2)

    def test_per_terminal_key_selection(self) -> None:
        key_a = bytes(range(12))
        key_b = bytes(range(12, 24))
        hsm = SpeckHSM(keys={1: key_a, 2: key_b})
        r2_1 = hsm.respond(W3_FIRST_C2, terminal_id=1)
        r2_2 = hsm.respond(W3_FIRST_C2, terminal_id=2)
        self.assertNotEqual(r2_1, r2_2)
        self.assertEqual(r2_1, Speck6496(key_a).encrypt(W3_FIRST_C2))
        self.assertEqual(r2_2, Speck6496(key_b).encrypt(W3_FIRST_C2))
        # Swapping keys swaps the responses (binding id -> key, not order).
        hsm.set_key(1, key_b)
        self.assertEqual(hsm.respond(W3_FIRST_C2, terminal_id=1), r2_2)

    def test_missing_key_or_id_raises_keyerror(self) -> None:
        hsm = SpeckHSM(keys={1: W3_KEY})
        with self.assertRaises(KeyError):
            hsm.respond(W3_FIRST_C2)  # no terminal_id at all
        with self.assertRaises(KeyError):
            hsm.respond(W3_FIRST_C2, terminal_id=99)  # unregistered id

    def test_bad_lengths_raise_valueerror(self) -> None:
        hsm = SpeckHSM()
        with self.assertRaises(ValueError):
            hsm.respond(bytes(7), terminal_id=1)  # C2 must be 8 bytes
        with self.assertRaises(ValueError):
            hsm.set_key(1, bytes(11))  # key must be 12 bytes
        self.assertEqual(DEVICE_KEY_BYTES, 12)

    def test_enroll_not_supported(self) -> None:
        with self.assertRaises(NotImplementedError):
            SpeckHSM().enroll(1)

    def test_status(self) -> None:
        hsm = SpeckHSM(keys={1: W3_KEY, 7: bytes(12)})
        self.assertEqual(
            hsm_status(hsm),
            {"backend": "speck64/96", "terminals_with_keys": 2},
        )


class TestDeviceKeyStore(TempDirTest):
    def test_key_persistence_across_restart(self) -> None:
        path = self.tmp / "keys.json"
        store = DeviceKeyStore(path)
        key, created = store.key_for(7)
        self.assertTrue(created)
        self.assertEqual(len(key), DEVICE_KEY_BYTES)
        # A second server run must reload the *same* key (A1 fix).
        key2, created2 = DeviceKeyStore(path).load().key_for(7)
        self.assertFalse(created2)
        self.assertEqual(key2, key)

    def test_keys_are_unique_per_terminal(self) -> None:
        store = DeviceKeyStore(self.tmp / "keys.json")
        k7, _ = store.key_for(7)
        k8, _ = store.key_for(8)
        self.assertNotEqual(k7, k8)

    def test_c2_history_roundtrip(self) -> None:
        path = self.tmp / "keys.json"
        store = DeviceKeyStore(path)
        store.set_key(7, W3_KEY)
        store.set_c2_history(7, [W3_FIRST_C2, bytes(8)])
        reloaded = DeviceKeyStore(path).load()
        self.assertEqual(reloaded.c2_history(7), [W3_FIRST_C2, bytes(8)])
        self.assertEqual(reloaded.all_keys(), {7: W3_KEY})

    def test_clear_c2_history(self) -> None:
        store = DeviceKeyStore(self.tmp / "keys.json")
        store.set_key(7, W3_KEY)
        store.set_c2_history(7, [W3_FIRST_C2])
        store.clear_c2_history(7)
        self.assertEqual(
            DeviceKeyStore(self.tmp / "keys.json").load().c2_history(7), []
        )

    def test_bad_schema_rejected(self) -> None:
        path = self.tmp / "keys.json"
        path.write_text(json.dumps({"schema": "evil/v9", "terminals": {}}),
                        encoding="utf-8")
        with self.assertRaises(ValueError):
            DeviceKeyStore(path).load()

    def test_terminals_not_a_mapping_rejected(self) -> None:
        """R2N5: 'terminals': [] must fail with a contextual ValueError."""
        path = self.tmp / "keys.json"
        path.write_text(json.dumps({"schema": "puf-drone-auth/device-keys/v1",
                                    "terminals": []}),
                        encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            DeviceKeyStore(path).load()
        self.assertIn("terminals", str(ctx.exception))

    def test_noncanonical_terminal_key_rejected(self) -> None:
        """TYPES-04: " 9 " style keys must not silently remap ids."""
        path = self.tmp / "keys.json"
        path.write_text(json.dumps(
            {"schema": "puf-drone-auth/device-keys/v1",
             "terminals": {" 9 ": {"key_hex": bytes(12).hex()}}}),
            encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            DeviceKeyStore(path).load()
        self.assertIn("canonical", str(ctx.exception))

    def test_mutator_rolls_back_on_save_failure(self) -> None:
        """R2N2: a mutation whose save fails must not linger in memory."""
        store = DeviceKeyStore(self.tmp / "keys.json")
        store.set_key(7, bytes(12))  # establishes terminal 7 on disk

        def boom(*_a, **_k):
            raise OSError("locked")

        real_save = store.save
        store.save = boom
        with self.assertRaises(OSError):
            store.set_key(7, bytes(range(12)))       # replacement fails
        with self.assertRaises(OSError):
            store.set_key(8, bytes(range(12)))       # fresh install fails
        store.save = real_save
        # In-memory state must equal the last persisted state.
        self.assertEqual(store.all_keys(), {7: bytes(12)})
        # And a later successful save must not resurrect the failed ones.
        store.set_key(9, bytes([9] * 12))
        reloaded = DeviceKeyStore(self.tmp / "keys.json").load()
        self.assertEqual(reloaded.all_keys().keys(), {7, 9})

    def test_file_permissions_owner_only(self) -> None:
        path = self.tmp / "keys.json"
        store = DeviceKeyStore(path)
        store.set_key(7, W3_KEY)
        if os.name == "nt":  # Windows ACLs: just assert existence here
            self.assertTrue(path.exists())
            return
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)

    def test_atomic_save_leaves_no_tmp(self) -> None:
        path = self.tmp / "keys.json"
        store = DeviceKeyStore(path)
        store.set_key(7, W3_KEY)
        store.save()
        leftovers = list(self.tmp.glob("*.tmp"))
        self.assertEqual(leftovers, [])


class ProtocolTestBase(TempDirTest):
    def build_protocol(self, hsm=None) -> HFIDAProtocol:
        templates = TemplateDB(self.tmp / "templates.json")
        templates.enroll(1, [(bytes([i] * 8), bytes(8)) for i in range(1, 9)])
        pools = CRPPoolRegistry(self.tmp / "pools", pool_size=100)
        # CRP pools start empty; reserve() is the enrollment path that
        # mints seeds into the pool (mirrors cmd_enroll before cmd_auth).
        pools.get(1).reserve(20)
        return HFIDAProtocol(
            templates=templates,
            hsm=hsm if hsm is not None else SpeckHSM(keys={1: W3_KEY}),
            pools=pools,
        )


class TestC2ReplayGuard(ProtocolTestBase):
    def test_duplicate_c2_rejected(self) -> None:
        proto = self.build_protocol()
        c2 = W3_FIRST_C2
        msg_id, _ = HFIDAProtocol.parse(proto.on_access_request(1, c2=c2))
        self.assertEqual(msg_id, HFIDAProtocol.MSG_CHALLENGE)
        # Same C2 again -> replayed ACCESS_REQUEST -> RESULT_REPLAY.
        msg_id2, f2 = HFIDAProtocol.parse(proto.on_access_request(1, c2=c2))
        self.assertEqual(msg_id2, HFIDAProtocol.MSG_RESULT)
        self.assertEqual(f2["result"], RESULT_REPLAY)
        # A fresh C2 is still accepted.
        c2_next = bytes((b + 1) & 0xFF for b in c2)
        msg_id3, _ = HFIDAProtocol.parse(proto.on_access_request(1, c2=c2_next))
        self.assertEqual(msg_id3, HFIDAProtocol.MSG_CHALLENGE)

    def test_history_hydration_and_reset(self) -> None:
        proto = self.build_protocol()
        proto.set_c2_history(1, [W3_FIRST_C2])
        msg_id, f = HFIDAProtocol.parse(proto.on_access_request(1, c2=W3_FIRST_C2))
        self.assertEqual((msg_id, f["result"]),
                         (HFIDAProtocol.MSG_RESULT, RESULT_REPLAY))
        proto.reset_c2_history(1)
        msg_id2, _ = HFIDAProtocol.parse(proto.on_access_request(1, c2=W3_FIRST_C2))
        self.assertEqual(msg_id2, HFIDAProtocol.MSG_CHALLENGE)

    def test_history_roundtrip_via_store(self) -> None:
        proto = self.build_protocol()
        proto.set_c2_history(1, [W3_FIRST_C2, bytes(8)])
        store = DeviceKeyStore(self.tmp / "keys.json")
        store.set_key(1, W3_KEY)
        store.set_c2_history(1, proto.c2_history(1))
        reloaded = DeviceKeyStore(self.tmp / "keys.json").load()
        proto2 = self.build_protocol()
        for tid in reloaded.all_keys():
            proto2.set_c2_history(tid, reloaded.c2_history(tid))
        self.assertEqual(proto2.c2_history(1), [W3_FIRST_C2, bytes(8)])

    def test_replay_window_is_bounded(self) -> None:
        proto = self.build_protocol()
        for n in range(1, HFIDAProtocol.C2_REPLAY_WINDOW + 2):
            c2 = bytes((b + n) & 0xFF for b in W3_FIRST_C2)
            proto._remember_c2(1, c2)
        self.assertLessEqual(len(proto.c2_history(1)),
                             HFIDAProtocol.C2_REPLAY_WINDOW)
        # The oldest value was evicted, the newest is remembered.
        oldest = bytes((b + 1) & 0xFF for b in W3_FIRST_C2)
        newest = bytes((b + HFIDAProtocol.C2_REPLAY_WINDOW + 1) & 0xFF
                       for b in W3_FIRST_C2)
        self.assertNotIn(oldest, proto.c2_history(1))
        self.assertIn(newest, proto.c2_history(1))


class TestEndToEnd(TempDirTest):
    def _enrolled_protocol(self):
        transport = LoopbackTransport()
        templates = TemplateDB(self.tmp / "templates.json")
        pools = CRPPoolRegistry(self.tmp / "pools", pool_size=100)
        proto = HFIDAProtocol(
            templates=templates,
            hsm=SpeckHSM(keys={1: W3_KEY}),
            pools=pools,
        )
        terminal = transport.terminal(1)
        seeds = pools.get(1).reserve(20)
        templates.enroll(1, [(s, terminal.ideal_response(s)) for s in seeds])
        return transport, proto

    def test_full_auth_round_uses_speck_r2(self) -> None:
        """PASS verdict carries R2 = Speck(K_terminal, C2) (not HMAC)."""
        transport, proto = self._enrolled_protocol()
        c2 = transport.counter_challenge(1)
        self.assertEqual(c2, W3_FIRST_C2)  # loopback now matches the RTL
        frame = proto.on_access_request(1, c2=c2)
        msg_id, fields = HFIDAProtocol.parse(frame)
        self.assertEqual(msg_id, HFIDAProtocol.MSG_CHALLENGE)
        r1s = transport.respond(1, fields["seeds"], flip_prob=0.0)
        msg2, f2 = HFIDAProtocol.parse(proto.on_response(1, r1s))
        self.assertEqual(msg2, HFIDAProtocol.MSG_RESULT)
        self.assertEqual(f2["result"], RESULT_PASS)
        self.assertEqual(f2["r2"], Speck6496(W3_KEY).encrypt(c2))
        self.assertEqual(f2["r2"], W3_FIRST_R2)

    def test_replayed_access_request_after_success_rejected(self) -> None:
        transport, proto = self._enrolled_protocol()
        c2 = transport.counter_challenge(1)
        frame = proto.on_access_request(1, c2=c2)
        _, fields = HFIDAProtocol.parse(frame)
        proto.on_response(1, transport.respond(1, fields["seeds"],
                                                flip_prob=0.0))
        # Replaying the identical ACCESS_REQUEST must now be refused.
        msg_id, f = HFIDAProtocol.parse(proto.on_access_request(1, c2=c2))
        self.assertEqual((msg_id, f["result"]),
                         (HFIDAProtocol.MSG_RESULT, RESULT_REPLAY))


class TestLateC2(TempDirTest):
    """P2-T2: late-bound / restated / conflicting C2 on response paths."""

    def _enrolled(self):
        transport = LoopbackTransport()
        templates = TemplateDB(self.tmp / "templates.json")
        pools = CRPPoolRegistry(self.tmp / "pools", pool_size=100)
        proto = HFIDAProtocol(
            templates=templates,
            hsm=SpeckHSM(keys={1: W3_KEY}),
            pools=pools,
        )
        terminal = transport.terminal(1)
        seeds = pools.get(1).reserve(20)
        templates.enroll(1, [(s, terminal.ideal_response(s)) for s in seeds])
        return transport, proto

    def test_late_binding_sets_r2(self) -> None:
        """C2 supplied at on_response (session started without one) drives R2."""
        transport, proto = self._enrolled()
        mid, f = HFIDAProtocol.parse(proto.start_auth(1))  # no c2
        self.assertEqual(mid, HFIDAProtocol.MSG_CHALLENGE)
        r1s = transport.respond(1, f["seeds"], flip_prob=0.0)
        mid2, f2 = HFIDAProtocol.parse(proto.on_response(1, r1s, c2=W3_FIRST_C2))
        self.assertEqual((mid2, f2["result"]),
                         (HFIDAProtocol.MSG_RESULT, RESULT_PASS))
        self.assertEqual(f2["r2"], W3_FIRST_R2)

    def test_late_binding_rejected_as_replay(self) -> None:
        """A late C2 must pass the replay window like an ACCESS_REQUEST."""
        transport, proto = self._enrolled()
        proto.set_c2_history(1, [W3_FIRST_C2])
        mid, f = HFIDAProtocol.parse(proto.start_auth(1))
        r1s = transport.respond(1, f["seeds"], flip_prob=0.0)
        with self.assertRaises(ProtocolError):
            proto.on_response(1, r1s, c2=W3_FIRST_C2)

    def test_c2_conflict_mid_session(self) -> None:
        """Restating the session C2 is fine; changing it is an error."""
        transport, proto = self._enrolled()
        c2 = transport.counter_challenge(1)
        mid, f = HFIDAProtocol.parse(proto.on_access_request(1, c2=c2))
        r1s = transport.respond(1, f["seeds"], flip_prob=0.0)
        other = bytes(b ^ 0xFF for b in c2)
        with self.assertRaises(ProtocolError):
            proto.on_response(1, r1s, c2=other)
        mid2, f2 = HFIDAProtocol.parse(proto.on_response(1, r1s, c2=c2))
        self.assertEqual(f2["result"], RESULT_PASS)
        self.assertEqual(f2["r2"], Speck6496(W3_KEY).encrypt(c2))

    def test_no_c2_fallback_r2_is_speck_of_zero_block(self) -> None:
        """Documented fallback: R2 = Speck(K, 0^8) when no C2 was bound."""
        transport, proto = self._enrolled()
        mid, f = HFIDAProtocol.parse(proto.start_auth(1))
        r1s = transport.respond(1, f["seeds"], flip_prob=0.0)
        mid2, f2 = HFIDAProtocol.parse(proto.on_response(1, r1s))
        self.assertEqual((mid2, f2["result"]),
                         (HFIDAProtocol.MSG_RESULT, RESULT_PASS))
        self.assertEqual(f2["r2"], Speck6496(W3_KEY).encrypt(bytes(8)))

    def test_hsm_failure_answers_result_error_frame(self) -> None:
        """A failing HSM yields RESULT_ERROR, not an escaped exception."""
        transport, proto = self._enrolled()
        proto.hsm = SpeckHSM()  # no keys -> respond raises KeyError
        mid, f = HFIDAProtocol.parse(proto.start_auth(1))
        r1s = transport.respond(1, f["seeds"], flip_prob=0.0)
        mid2, f2 = HFIDAProtocol.parse(proto.on_response(1, r1s, c2=W3_FIRST_C2))
        self.assertEqual((mid2, f2["result"], f2["hd"]),
                         (HFIDAProtocol.MSG_RESULT, 2, 0xFF))


class TestRestartReplayE2E(TempDirTest):
    """P2-T3: the C2 replay window must survive a server restart."""

    def test_replayed_c2_refused_after_restart(self) -> None:
        from src.python.server.main import _ensure_device_key, _flush_c2_state

        keys_path = self.tmp / "keys.json"
        transport = LoopbackTransport()

        # --- server run #1 (wiring mirrors main()) ---
        store1 = DeviceKeyStore(keys_path)
        templates = TemplateDB(self.tmp / "templates.json")
        pools = CRPPoolRegistry(self.tmp / "pools", pool_size=100)
        terminal = transport.terminal(1)
        seeds = pools.get(1).reserve(20)
        templates.enroll(1, [(s, terminal.ideal_response(s)) for s in seeds])
        proto1 = HFIDAProtocol(
            templates=templates, hsm=SpeckHSM(keys=store1.all_keys()), pools=pools
        )
        with contextlib.redirect_stdout(io.StringIO()):
            _ensure_device_key(store1, proto1, 1)  # mint + persist key

        c2 = transport.counter_challenge(1)  # terminal's first C2 (a1..a8)
        mid, _ = HFIDAProtocol.parse(proto1.on_access_request(1, c2=c2))
        self.assertEqual(mid, HFIDAProtocol.MSG_CHALLENGE)
        _flush_c2_state(proto1, store1)  # main() persists here

        # --- "restart": fresh store / HSM / protocol from the same paths ---
        store2 = DeviceKeyStore(keys_path).load()
        hsm2 = SpeckHSM(keys=store2.all_keys())
        self.assertTrue(hsm2.has_key(1))
        templates2 = TemplateDB(self.tmp / "templates.json")
        pools2 = CRPPoolRegistry(self.tmp / "pools", pool_size=100)
        proto2 = HFIDAProtocol(templates=templates2, hsm=hsm2, pools=pools2)
        for tid in hsm2.terminal_ids():
            proto2.set_c2_history(tid, store2.c2_history(tid))
        # Replaying run-1's ACCESS_REQUEST must be refused (RESULT_REPLAY).
        mid2, f2 = HFIDAProtocol.parse(proto2.on_access_request(1, c2=c2))
        self.assertEqual((mid2, f2["result"]),
                         (HFIDAProtocol.MSG_RESULT, RESULT_REPLAY))
        # A genuinely fresh C2 from the still-powered terminal is accepted.
        c2_next = transport.counter_challenge(1)
        mid3, _ = HFIDAProtocol.parse(proto2.on_access_request(1, c2=c2_next))
        self.assertEqual(mid3, HFIDAProtocol.MSG_CHALLENGE)


class TestMainGlue(TempDirTest):
    """P2-T1: main-layer REPL / persistence glue coverage."""

    def _build(self):
        store = DeviceKeyStore(self.tmp / "keys.json")
        templates = TemplateDB(self.tmp / "templates.json")
        templates.enroll(1, [(bytes([i] * 8), bytes(8)) for i in range(1, 9)])
        pools = CRPPoolRegistry(self.tmp / "pools", pool_size=100)
        pools.get(1).reserve(20)
        proto = HFIDAProtocol(
            templates=templates, hsm=SpeckHSM(keys=store.all_keys()), pools=pools
        )
        return store, proto

    def test_ensure_skips_unknown_and_negative_ids(self) -> None:
        from src.python.server.main import _ensure_device_key

        store, proto = self._build()
        with contextlib.redirect_stdout(io.StringIO()):
            _ensure_device_key(store, proto, 99)   # typo must not mint keys
            _ensure_device_key(store, proto, -5)   # u32 wire domain
        self.assertEqual(store.all_keys(), {})
        self.assertEqual(proto.hsm.terminal_ids(), [])

    def test_ensure_mints_only_for_enrolled_terminal(self) -> None:
        from src.python.server.main import _ensure_device_key

        store, proto = self._build()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            _ensure_device_key(store, proto, 1)
        self.assertTrue(proto.hsm.has_key(1))
        self.assertIn("new Speck64/96 device key", out.getvalue())
        self.assertEqual(
            DeviceKeyStore(self.tmp / "keys.json").load().all_keys().keys(), {1}
        )
        with contextlib.redirect_stdout(io.StringIO()):
            _ensure_device_key(store, proto, 1)  # idempotent
        self.assertEqual(
            len(DeviceKeyStore(self.tmp / "keys.json").load().all_keys()), 1
        )

    def test_cmd_setkey_flow(self) -> None:
        from src.python.server.main import cmd_setkey

        store, proto = self._build()
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_setkey(proto, store, ["1", W3_KEY.hex()])
        self.assertEqual(proto.hsm.respond(W3_FIRST_C2, terminal_id=1), W3_FIRST_R2)
        self.assertEqual(
            DeviceKeyStore(self.tmp / "keys.json").load().all_keys()[1], W3_KEY
        )
        for bad in (["1", "zz"], ["1", "abcd"], ["-5", W3_KEY.hex()], ["1"], []):
            with contextlib.redirect_stdout(io.StringIO()):
                cmd_setkey(proto, store, bad)
        self.assertEqual(
            DeviceKeyStore(self.tmp / "keys.json").load().all_keys(), {1: W3_KEY}
        )

    def test_cmd_c2reset_flow(self) -> None:
        from src.python.server.main import cmd_c2reset, cmd_setkey

        store, proto = self._build()
        with contextlib.redirect_stdout(io.StringIO()):
            cmd_setkey(proto, store, ["1", W3_KEY.hex()])
        proto.set_c2_history(1, [W3_FIRST_C2])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cmd_c2reset(proto, store, ["1"])
        self.assertIn("replay window cleared", out.getvalue())
        self.assertEqual(proto.c2_history(1), [])
        self.assertEqual(
            DeviceKeyStore(self.tmp / "keys.json").load().c2_history(1), []
        )
        mid, _ = HFIDAProtocol.parse(proto.on_access_request(1, c2=W3_FIRST_C2))
        self.assertEqual(mid, HFIDAProtocol.MSG_CHALLENGE)

    def test_flush_persists_and_swallows_oserror(self) -> None:
        from src.python.server.main import _ensure_device_key, _flush_c2_state

        store, proto = self._build()
        with contextlib.redirect_stdout(io.StringIO()):
            _ensure_device_key(store, proto, 1)
        HFIDAProtocol.parse(proto.on_access_request(1, c2=W3_FIRST_C2))
        _flush_c2_state(proto, store)
        self.assertEqual(
            DeviceKeyStore(self.tmp / "keys.json").load().c2_history(1),
            [W3_FIRST_C2],
        )

        def boom(*_a, **_k):
            raise OSError("disk on fire")

        store.set_c2_history = boom
        with contextlib.redirect_stdout(io.StringIO()) as out:
            _flush_c2_state(proto, store)  # must not raise
        self.assertIn("persistence failed", out.getvalue())

    def test_repl_survives_store_oserror(self) -> None:
        from src.python.server.main import repl

        store, proto = self._build()

        def boom(*_a, **_k):
            raise OSError("file locked by AV")

        store.set_key = boom
        lines = iter(["setkey 1 " + W3_KEY.hex(), "quit"])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = repl(proto, LoopbackTransport(), 3, store,
                      input_fn=lambda _p: next(lines))
        self.assertEqual(rc, 0)
        self.assertIn("[ERROR]", out.getvalue())

    def test_repl_smoke_setkey_auth_quit_golden_r2(self) -> None:
        from src.python.server.main import repl

        transport = LoopbackTransport()
        templates = TemplateDB(self.tmp / "templates.json")
        pools = CRPPoolRegistry(self.tmp / "pools", pool_size=100)
        store = DeviceKeyStore(self.tmp / "keys.json")
        proto = HFIDAProtocol(
            templates=templates, hsm=SpeckHSM(keys=store.all_keys()), pools=pools
        )
        terminal = transport.terminal(1)
        seeds = pools.get(1).reserve(20)
        templates.enroll(1, [(s, terminal.ideal_response(s)) for s in seeds])
        terminal.flip_prob = 0.0  # deterministic PASS verdict
        lines = iter(["setkey 1 " + W3_KEY.hex(), "auth 1", "quit"])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = repl(proto, transport, 3, store, input_fn=lambda _p: next(lines))
        self.assertEqual(rc, 0)
        self.assertIn("PASS", out.getvalue())
        self.assertIn("7b45b0545e59aa94", out.getvalue())  # golden R2

    def test_cmd_enroll_mints_key_after_enrollment(self) -> None:
        """tests-r2 N2: the enroll command keys the terminal only after the
        template exists (mint-timing regression guard, mutation MUT-B)."""
        from src.python.server.main import cmd_enroll

        transport = LoopbackTransport()
        templates = TemplateDB(self.tmp / "templates.json")
        pools = CRPPoolRegistry(self.tmp / "pools", pool_size=100)
        store = DeviceKeyStore(self.tmp / "keys.json")
        proto = HFIDAProtocol(
            templates=templates, hsm=SpeckHSM(keys=store.all_keys()),
            pools=pools,
        )
        with contextlib.redirect_stdout(io.StringIO()) as out:
            cmd_enroll(proto, transport, ["1", "8"], 3, store)
        self.assertTrue(proto.templates.has_terminal(1))
        self.assertTrue(proto.hsm.has_key(1))
        self.assertIn(1, DeviceKeyStore(self.tmp / "keys.json").load().all_keys())
        self.assertIn("new Speck64/96 device key", out.getvalue())

    def test_repl_spoof_rejects_impostor(self) -> None:
        """tests-r2 N3: the spoof path answers with an impostor device and
        must end in a REJECT verdict."""
        from src.python.server.main import repl

        transport = LoopbackTransport()
        templates = TemplateDB(self.tmp / "templates.json")
        pools = CRPPoolRegistry(self.tmp / "pools", pool_size=100)
        store = DeviceKeyStore(self.tmp / "keys.json")
        proto = HFIDAProtocol(
            templates=templates, hsm=SpeckHSM(keys={1: W3_KEY}), pools=pools
        )
        terminal = transport.terminal(1)
        seeds = pools.get(1).reserve(20)
        templates.enroll(1, [(s, terminal.ideal_response(s)) for s in seeds])
        lines = iter(["spoof 1", "quit"])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = repl(proto, transport, 3, store, input_fn=lambda _p: next(lines))
        self.assertEqual(rc, 0)
        self.assertIn("REJECT", out.getvalue())


def _enrolled_pair(tmp: Path):
    """Shared fixture: enrolled loopback terminal + protocol with W3 key."""
    transport = LoopbackTransport()
    templates = TemplateDB(tmp / "templates.json")
    pools = CRPPoolRegistry(tmp / "pools", pool_size=100)
    proto = HFIDAProtocol(
        templates=templates,
        hsm=SpeckHSM(keys={1: W3_KEY}),
        pools=pools,
    )
    terminal = transport.terminal(1)
    seeds = pools.get(1).reserve(20)
    templates.enroll(1, [(s, terminal.ideal_response(s)) for s in seeds])
    return transport, proto


def _responses_with_flips(transport: LoopbackTransport, seeds, n_flips: int):
    """Deterministic responses with exactly n_flips distinct bit errors each.

    n_flips=0 reproduces ideal_response; n_flips=10 per response lands the
    aggregate score in the gray zone (TAU_PASS=6, TAU_REJECT=16).
    """
    terminal = transport.terminal(1)
    out = []
    for seed in seeds:
        value = int.from_bytes(terminal.ideal_response(seed), "big")
        for i in range(n_flips):
            value ^= 1 << ((i * 3) % 64)  # distinct bit positions
        out.append(value.to_bytes(8, "big"))
    return out


class TestGrayZone(TempDirTest):
    """tests-r2 N1: the gray-zone re-test path (on_extra_response).

    Covers MSG_EXTRA_CHALLENGE, aggregate scaled-threshold scoring over 7
    responses, _finish_reject, and the second _update_session_c2 call site
    (protocol.py on_extra_response) for bind / restate / conflict.
    """

    def test_gray_then_perfect_extra_passes(self) -> None:
        transport, proto = _enrolled_pair(self.tmp)
        mid, f = HFIDAProtocol.parse(
            proto.on_access_request(1, c2=W3_FIRST_C2)
        )
        r1s = _responses_with_flips(transport, f["seeds"], n_flips=10)
        mid2, f2 = HFIDAProtocol.parse(proto.on_response(1, r1s))
        self.assertEqual((mid2, len(f2["seeds"])),
                         (HFIDAProtocol.MSG_EXTRA_CHALLENGE, 3))
        # Perfect extra responses pull the aggregate back into PASS.
        r1x = _responses_with_flips(transport, f2["seeds"], n_flips=0)
        mid3, f3 = HFIDAProtocol.parse(
            proto.on_extra_response(1, r1x, c2=W3_FIRST_C2)  # restate
        )
        self.assertEqual((mid3, f3["result"]),
                         (HFIDAProtocol.MSG_RESULT, RESULT_PASS))
        self.assertEqual(f3["r2"], W3_FIRST_R2)

    def test_gray_persisting_errors_reject(self) -> None:
        transport, proto = _enrolled_pair(self.tmp)
        mid, f = HFIDAProtocol.parse(
            proto.on_access_request(1, c2=W3_FIRST_C2)
        )
        r1s = _responses_with_flips(transport, f["seeds"], n_flips=10)
        _, f2 = HFIDAProtocol.parse(proto.on_response(1, r1s))
        r1x = _responses_with_flips(transport, f2["seeds"], n_flips=10)
        mid3, f3 = HFIDAProtocol.parse(proto.on_extra_response(1, r1x))
        self.assertEqual((mid3, f3["result"]),
                         (HFIDAProtocol.MSG_RESULT, 1))  # RESULT_REJECT

    def test_gray_late_c2_binding(self) -> None:
        """Session started without C2 binds it on the extra-response path."""
        transport, proto = _enrolled_pair(self.tmp)
        mid, f = HFIDAProtocol.parse(proto.start_auth(1))
        r1s = _responses_with_flips(transport, f["seeds"], n_flips=10)
        _, f2 = HFIDAProtocol.parse(proto.on_response(1, r1s))
        r1x = _responses_with_flips(transport, f2["seeds"], n_flips=0)
        mid3, f3 = HFIDAProtocol.parse(
            proto.on_extra_response(1, r1x, c2=W3_FIRST_C2)
        )
        self.assertEqual((mid3, f3["result"]),
                         (HFIDAProtocol.MSG_RESULT, RESULT_PASS))
        self.assertEqual(f3["r2"], W3_FIRST_R2)

    def test_gray_failed_c2_attempt_does_not_double_count(self) -> None:
        """R2N1 regression: a failed extra-response attempt must leave the
        session untouched, so a corrected retry decides on clean scores.

        Buggy order (score-then-validate) turned this scenario into a
        silent REJECT: 4x7=28 gray, failed attempt carrying 3x8=24,
        clean retry -> 28+24+0=52 > 42 instead of the correct 28 <= 42.
        """
        transport, proto = _enrolled_pair(self.tmp)
        c2 = transport.counter_challenge(1)
        mid, f = HFIDAProtocol.parse(proto.on_access_request(1, c2=c2))
        r1s = _responses_with_flips(transport, f["seeds"], n_flips=7)  # 28
        mid2, f2 = HFIDAProtocol.parse(proto.on_response(1, r1s))
        self.assertEqual(mid2, HFIDAProtocol.MSG_EXTRA_CHALLENGE)
        other = bytes(b ^ 0xFF for b in c2)
        with self.assertRaises(ProtocolError):
            proto.on_extra_response(  # failed attempt carries 3x8=24
                1, _responses_with_flips(transport, f2["seeds"], n_flips=8),
                c2=other,
            )
        # Corrected retry with clean responses must PASS, not double-count.
        r1x = _responses_with_flips(transport, f2["seeds"], n_flips=0)
        mid3, f3 = HFIDAProtocol.parse(proto.on_extra_response(1, r1x, c2=c2))
        self.assertEqual((mid3, f3["result"], f3["hd"]),
                         (HFIDAProtocol.MSG_RESULT, RESULT_PASS, 28))
        self.assertEqual(f3["r2"], Speck6496(W3_KEY).encrypt(c2))

    def test_gray_c2_conflict_mid_session(self) -> None:
        transport, proto = _enrolled_pair(self.tmp)
        c2 = transport.counter_challenge(1)
        mid, f = HFIDAProtocol.parse(proto.on_access_request(1, c2=c2))
        r1s = _responses_with_flips(transport, f["seeds"], n_flips=10)
        _, f2 = HFIDAProtocol.parse(proto.on_response(1, r1s))
        r1x = _responses_with_flips(transport, f2["seeds"], n_flips=0)
        other = bytes(b ^ 0xFF for b in c2)
        with self.assertRaises(ProtocolError):
            proto.on_extra_response(1, r1x, c2=other)
        # Restating the bound C2 still completes the session.
        mid3, f3 = HFIDAProtocol.parse(
            proto.on_extra_response(1, r1x, c2=c2)
        )
        self.assertEqual(f3["result"], RESULT_PASS)
        self.assertEqual(f3["r2"], Speck6496(W3_KEY).encrypt(c2))


class TestParseLengthValidation(unittest.TestCase):
    """R2N4: every fixed-layout message rejects wrong payload lengths."""

    def _frame(self, msg_id: int, payload: bytes) -> bytes:
        """Build a CRC-valid frame around an arbitrary payload."""
        header = bytes([0xFD, len(payload), 0, 0, 0, 1, 2,
                        msg_id & 0xFF, (msg_id >> 8) & 0xFF, 0])
        crc = crc16_mcrf4xx(
            header[1:] + payload + bytes([HFIDAProtocol._crc_extra(msg_id)])
        )
        return header + payload + struct.pack("<H", crc)

    def test_short_result_and_confirm_payloads_rejected(self) -> None:
        for msg_id, bad in ((0x0093, b"\x00\x05\xaa"),      # RESULT, 3B
                            (0x0094, b"\x01\x00\x00\x00")):  # CONFIRM, 4B
            with self.assertRaises(ValueError) as ctx:
                HFIDAProtocol.parse(self._frame(msg_id, bad))
            self.assertIn("must be", str(ctx.exception))
        # Sanity: full-length payloads still parse.
        mid, f = HFIDAProtocol.parse(
            self._frame(0x0093, b"\x00\x05" + bytes(8))
        )
        self.assertEqual((mid, f["result"], f["hd"]), (0x0093, 0, 5))


class TestSimulatedTerminalC2(unittest.TestCase):
    def test_c2_sequence_matches_rtl_contract(self) -> None:
        from src.python.server.main import SimulatedTerminal

        term = SimulatedTerminal(1)
        self.assertEqual(term.counter_challenge(), W3_FIRST_C2)
        self.assertEqual(term.counter_challenge(),
                         bytes.fromhex("a2a3a4a5a6a7a8a9"))
        self.assertEqual(term.counter_challenge(),
                         bytes.fromhex("a3a4a5a6a7a8a9aa"))
        # Exact RTL wraparound, no carry propagation: byte j is
        # (0xA0 + j + n) & 0xFF, so at n = 0x60 byte 0 wraps first and
        # C2 becomes exactly 00 01 02 ... 07 (terminal_fsm.v semantics).
        term._auth_count = 0x5F
        self.assertEqual(term.counter_challenge(), bytes(range(8)))
        self.assertEqual(term.counter_challenge(),
                         bytes(b + 1 for b in range(8)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
