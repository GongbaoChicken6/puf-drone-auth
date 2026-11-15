"""fan_relay.py - PC-side fan speed relay for drone demo.

Reads DroneSim state from web bridge /api/status, maps altitude/state
to PWM value, sends via third USB-TTL serial port + HC-12 (C002, 9600)
to remote Arduino fan node.

Usage: python tools/fan/fan_relay.py --port COM10
Exit: Ctrl+C or serial error → fan stops via Arduino watchdog (3s).
"""
import argparse
import json
import sys
import time
import urllib.request

try:
    import serial
except ImportError:
    print("pip install pyserial", file=sys.stderr)
    sys.exit(1)


def get_drone_state(base_url):
    """Returns (unlocked, alt, state)."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/status", timeout=2) as r:
            st = json.loads(r.read())
        drone = st.get("drone", {}).get("tids", {})
        for tid, d in drone.items():
            return bool(d.get("unlocked")), d.get("pos", [0, 0, 0])[2], d.get("state", "")
        return False, 0.0, ""
    except Exception:
        return False, 0.0, ""


def calc_pwm(unlocked, alt, state):
    """Map flight state to PWM 0-255 (review fix: ARMED idle speed)."""
    if not unlocked:
        return 0                    # locked = stop
    if state == "ARMED":
        return 50                   # idle: slow spin = "ready to fly" (review P2)
    if state == "LAND":
        return int(alt * 40)        # descending: proportional to altitude
    if state == "TAKEOFF":
        return 120 + int(alt * 30)  # climbing: medium + altitude boost
    if state == "HOVER":
        return 150                  # hovering: medium
    if state in ("MOVE", "RTL"):
        return 200                  # cruising: fast
    return int(alt * 50)            # LANDED/other: altitude-proportional (0 at ground)


def make_frame(speed):
    s = max(0, min(255, speed))
    return bytes([0xAA, s, (~s) & 0xFF])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, default=9600)
    p.add_argument("--bridge", default="http://127.0.0.1:8642")
    p.add_argument("--interval-ms", type=int, default=100)
    args = p.parse_args()

    ser = None
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
        print(f"[FAN] relay {args.port}@{args.baud} -> {args.bridge}",
              file=sys.stderr)
        print(f"[FAN] Ctrl+C to stop (fan auto-stops via watchdog in 3s)",
              file=sys.stderr)
        last = -1
        while True:
            unlocked, alt, state = get_drone_state(args.bridge)
            pwm = calc_pwm(unlocked, alt, state)
            if pwm != last:
                print(f"[FAN] {state:8s} alt={alt:.1f}m pwm={pwm}",
                      file=sys.stderr)
                last = pwm
            ser.write(make_frame(pwm))
            time.sleep(args.interval_ms / 1000)
    except KeyboardInterrupt:
        print("[FAN] stopped by user (fan auto-stops in 3s)", file=sys.stderr)
    except serial.SerialException as e:
        print(f"[FAN] serial error: {e} (fan auto-stops in 3s)", file=sys.stderr)
    finally:
        if ser is not None:
            try:
                ser.write(make_frame(0))  # send stop command as courtesy
                ser.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
