"""hc12_config_c002.py - Configure a pair of HC-12 to channel C002 @ 9600.

This is for the FAN CONTROL link (separate from auth link C001/115200).
Usage: python tools/hc12/hc12_config_c002.py --port COM7
"""
import argparse
import sys
import time

try:
    import serial
except ImportError:
    print("pip install pyserial", file=sys.stderr)
    sys.exit(1)


def try_at(ser, cmd, expect_prefix="OK+"):
    """Send AT command and read response."""
    ser.reset_input_buffer()
    ser.write((cmd + "\r\n").encode())
    time.sleep(0.3)
    resp = ser.read(256).decode("ascii", errors="replace").strip()
    print(f"  {cmd:20s} -> {resp!r}")
    return resp if resp.startswith(expect_prefix) else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True, help="COM port of HC-12")
    p.add_argument("--channel", default="C002")
    p.add_argument("--baud", type=int, default=9600)
    args = p.parse_args()

    print(f"\n=== HC-12 Fan Link Config: {args.port} ===")

    # HC-12 AT mode: hold SET pin LOW, or send AT+... at current baud
    # Try at 9600 first (most common default for HC-12 AT mode)
    for session_baud in [9600, 115200]:
        print(f"\nTrying AT session at {session_baud} baud...")
        ser = serial.Serial(args.port, session_baud, timeout=1)
        time.sleep(0.5)

        # Test AT
        resp = try_at(ser, "AT")
        if resp is None:
            print(f"  No response at {session_baud}, trying next...")
            ser.close()
            continue

        # Read current config
        print("  Current config:")
        try_at(ser, "AT+RX")

        # Set channel
        ch_resp = try_at(ser, f"AT+CHANNEL={args.channel}")
        if ch_resp is None:
            print(f"  FAILED to set channel {args.channel}")
            ser.close()
            sys.exit(1)

        # Set baud
        bd_resp = try_at(ser, f"AT+BAUD={args.baud}")
        if bd_resp is None:
            print(f"  FAILED to set baud {args.baud}")
            ser.close()
            sys.exit(1)

        # Verify
        print("  Verifying...")
        time.sleep(0.5)
        if session_baud != args.baud:
            # After baud change, need to reopen at new baud
            ser.close()
            ser = serial.Serial(args.port, args.baud, timeout=1)
            time.sleep(0.5)

        vr = try_at(ser, "AT+RX")
        if vr and args.channel in vr and str(args.baud) in vr:
            print(f"  \u2705 SUCCESS: {args.channel} @ {args.baud}")
        else:
            print(f"  \u26a0 Verify response may not show all params: {vr}")

        ser.close()
        return 0

    print("\n\u274c No AT response at any baud. Check wiring:")
    print("  HC-12 SET pin must be held LOW (connect to GND) during config")
    print("  Or: HC-12 defaults to AT mode when powered with SET grounded")
    sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
