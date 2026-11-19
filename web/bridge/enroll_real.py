"""enroll_real.py -- N5(finals-demo): True-board enrollment runner.

Bridge-side enrollment for real serial boards. web_bridge.py wires this in
with 3 touchpoints (import + init + route); all logic lives here.

Transport: sends CHALLENGE frames via the listener's serial port, collects
RESPONSE_R1 frames routed by the listener when enroll_session_active=True,
feeds them into the existing enroll_device() (majority vote + template build).
"""
from __future__ import annotations

from queue import Empty


def submit_enroll_real(app, tid: int, n: int, measurements: int) -> str:
    """Submit an enrollment job to the orchestrator."""
    run_id = app.orch.next_run_id()
    app.orch.submit(_make_job(app, tid, n, measurements, run_id))
    return run_id


def _make_job(app, tid, n, measurements, run_id):
    """Create a Job with a custom runner (avoids modifying Job class)."""
    from web_bridge import Job
    job = Job(kind="enroll_real", tid=tid, n=n,
              measurements=measurements, run_id=run_id)
    job._runner = lambda: _do_enroll_real(app, job)
    return job


def _do_enroll_real(app, job) -> str:
    """Enrollment runner: CHALLENGE->RESPONSE loop via listener queue."""
    tid = int(job.tid or 0)
    n = max(4, int(job.n or 100))
    rounds = max(1, int(job.measurements or 3))
    run_id = job.run_id
    # 多口(N6)路由修复:双串口下 app.serial_listener 只是第一个口,
    # 会把握手帧打到别的板;先按 tid 路由(resolve_listener),再回退。
    ln = None
    _resolve = getattr(app, "resolve_listener", None)
    if _resolve is not None:
        try:
            ln = _resolve(tid)
        except Exception:
            ln = None
    if ln is None:
        ln = getattr(app, "serial_listener", None)
    if ln is None or not getattr(ln, "running", False):
        app.hub.publish("run.error", {
            "run_id": run_id, "stage": "enroll_real", "terminal_id": tid,
            "error": "enroll_real requires real-serial mode (--serial-port)"})
        return run_id

    def progress(batch, batches, rnd, rounds_):
        app.hub.publish("enroll.progress", {
            "run_id": run_id, "terminal_id": tid,
            "batch": batch, "batches": batches,
            "round": rnd, "rounds": rounds_})

    app.enroll_session_active = True
    try:
        while not app.enroll_response_q.empty():
            app.enroll_response_q.get_nowait()

        class _Transport:
            def respond(self, tid_, batch, frame=None):
                while not app.enroll_response_q.empty():
                    app.enroll_response_q.get_nowait()
                # N14(单信道): 共享信道下必须点名——先发 AUTH_POLL(tid, nonce=0) 打开
                # 该板的授权窗口（nonce=0 = 只开窗、不起认证），紧跟着的 CHALLENGE
                # 才会被它接受；另一块板没被点名 -> 不开窗 -> 自动丢弃。
                _arm = app.protocol.pack(
                    type(app.protocol).MSG_AUTH_POLL, terminal_id=tid_, nonce=0)
                with app.serial_bus_lock:
                    ln.ser.write(_arm)
                    ln.ser.flush()
                    ln.ser.write(frame)
                    ln.ser.flush()
                app.hub.publish("frame.tx", {
                    "run_id": run_id, "terminal_id": tid_,
                    "msg_id": 0x0091, "name": "CHALLENGE",
                    "hex": frame.hex(), "len": len(frame),
                    "dir": "server->term", "source": "real-enroll"})
                try:
                    fl = app.enroll_response_q.get(timeout=5.0)
                    return fl["r1s"]
                except Empty:
                    raise TimeoutError(
                        "No RESPONSE_R1 within 5s -- board not in enroll mode?")

        pool = app.protocol.pools.get(tid)
        if pool.available_count + n > pool.pool_size:
            pool.reset()
            app.protocol.templates.templates[str(tid)] = {}
            app.protocol.templates.stability.pop(str(tid), None)

        result = app.mods.enroll_device(
            app.protocol, _Transport(), tid,
            n_challenges=n, measurements=rounds, on_progress=progress)
        s = result["summary"]
        app.real_serial_tids.add(tid)
        app.persist_terminal(tid)
        # N13: 录入后限池——只允许有模板对的种子被认证抽中
        # (否则 KeyError 'no template for seed ...'，2026-11-19 真板复现)
        try:
            _tpl = app.protocol.templates.templates.get(str(tid)) or {}
            pool.limit_to(_tpl.keys())
        except Exception as _le:  # noqa: BLE001 —— 限池失败不阻断录入成功
            app.hub.publish("server.log", {"level": "warn",
                "msg": f"enroll limit_to failed: {type(_le).__name__}: {_le}"})
        app.hub.publish("enroll.done", {
            "terminal_id": tid,
            "n_pairs": s.get("n_pairs", n),
            "added": s.get("added", n),
            "stable_bits": s.get("stable_bits", 0),
            "stability_pct": s.get("stability_pct", 0),
            "pool": app.orch._pool_payload(tid),
            "source": "real"})
        return run_id
    except Exception as exc:
        app.hub.publish("run.error", {
            "run_id": run_id, "stage": "enroll_real",
            "terminal_id": tid, "error": str(exc)})
        return run_id
    finally:
        app.enroll_session_active = False
