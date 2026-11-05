#!/usr/bin/env python3
"""
JetKVM Client CLI with Frame-Diff Stabilization Detection

Features:
- Captures snapshots
- Emulates keyboard and mouse actions via JetKVM JSON-RPC/REST
- Controls virtual media and ATX power
- Intelligent wait-for-change & wait-for-settle (diff-based throttling)
"""

import argparse
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def get_connection_info(args):
    host = (getattr(args, "host", None) or os.environ.get("JETKVM_HOST", "http://192.168.1.100")).rstrip("/")
    password = getattr(args, "password", None) or os.environ.get("JETKVM_PASSWORD", "")
    return host, password


def make_request(host, endpoint, data=None, method="POST", password=""):
    url = f"{host}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if password:
        headers["X-JetKVM-Auth"] = password

    payload = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if "image" in content_type:
                return resp.read()
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.URLError as e:
        print(f"Error connecting to JetKVM at {url}: {e}", file=sys.stderr)
        sys.exit(1)


def fetch_raw_snapshot(host, password=""):
    url = f"{host}/api/v1/snapshot"
    headers = {}
    if password:
        headers["X-JetKVM-Auth"] = password

    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.read()


def compute_frame_diff(img1_bytes, img2_bytes, downsample=(160, 90)):
    """
    Computes percentage of pixel intensity changes between two images.
    Returns float 0.0 to 100.0 (percentage difference).
    """
    if not HAS_PIL:
        # Fallback to byte-level sample diff if PIL is not installed
        l1, l2 = len(img1_bytes), len(img2_bytes)
        min_l = min(l1, l2)
        if min_l == 0:
            return 100.0
        step = max(1, min_l // 5000)
        diff_count = sum(1 for i in range(0, min_l, step) if img1_bytes[i] != img2_bytes[i])
        total_samples = min_l // step
        return (diff_count / total_samples) * 100.0

    im1 = Image.open(io.BytesIO(img1_bytes)).convert("L").resize(downsample)
    im2 = Image.open(io.BytesIO(img2_bytes)).convert("L").resize(downsample)

    p1 = list(im1.getdata())
    p2 = list(im2.getdata())

    threshold = 15  # noise filter for video compression artifacts
    diff_pixels = sum(1 for a, b in zip(p1, p2) if abs(a - b) > threshold)
    return (diff_pixels / len(p1)) * 100.0


def cmd_screenshot(args):
    host, password = get_connection_info(args)
    image_data = fetch_raw_snapshot(host, password)
    with open(args.output, "wb") as f:
        f.write(image_data)
    print(f"Screenshot saved to {args.output} ({len(image_data)} bytes)")


def cmd_wait_change(args):
    """
    Monitors frames until a state change is detected.
    Mode 'change': Wait until diff exceeds threshold (detects screen transition).
    Mode 'settle': Wait until diff stays below threshold (detects progress completion/settling).
    """
    host, password = get_connection_info(args)
    interval = args.interval
    timeout = args.timeout
    threshold = args.threshold
    mode = args.mode

    print(f"Monitoring screen in '{mode}' mode (threshold: {threshold}%, interval: {interval}s, timeout: {timeout}s)...")
    start_time = time.time()

    prev_frame = fetch_raw_snapshot(host, password)
    stable_consecutive = 0

    while time.time() - start_time < timeout:
        time.sleep(interval)
        curr_frame = fetch_raw_snapshot(host, password)
        diff = compute_frame_diff(prev_frame, curr_frame)
        elapsed = int(time.time() - start_time)

        print(f"[{elapsed}s] Frame diff: {diff:.2f}%")

        if mode == "change":
            if diff >= threshold:
                print(f"Change detected! Diff: {diff:.2f}% >= {threshold}%")
                if args.output:
                    with open(args.output, "wb") as f:
                        f.write(curr_frame)
                    print(f"Result snapshot saved to {args.output}")
                return
        elif mode == "settle":
            # Screen settled: small difference for N consecutive samples
            if diff < threshold:
                stable_consecutive += 1
                if stable_consecutive >= args.stable_frames:
                    print(f"Screen settled! Stable for {stable_consecutive} samples.")
                    if args.output:
                        with open(args.output, "wb") as f:
                            f.write(curr_frame)
                        print(f"Settled snapshot saved to {args.output}")
                    return
            else:
                stable_consecutive = 0

        prev_frame = curr_frame

    print(f"Timed out after {timeout} seconds.", file=sys.stderr)
    if args.output:
        with open(args.output, "wb") as f:
            f.write(curr_frame)


def cmd_click(args):
    host, password = get_connection_info(args)
    payload = {
        "action": "click",
        "x": args.x,
        "y": args.y,
        "button": args.button,
        "double": args.double,
    }
    resp = make_request(host, "/api/v1/hid/mouse", payload, password=password)
    print(f"Mouse click at ({args.x}, {args.y}): {resp}")


def cmd_type(args):
    host, password = get_connection_info(args)
    payload = {
        "action": "type",
        "text": args.text,
        "delay_ms": args.delay,
    }
    resp = make_request(host, "/api/v1/hid/keyboard", payload, password=password)
    print(f"Typed text: {args.text}")


def cmd_press(args):
    host, password = get_connection_info(args)
    payload = {
        "action": "press",
        "key": args.key,
        "modifiers": args.modifiers or [],
    }
    resp = make_request(host, "/api/v1/hid/keyboard", payload, password=password)
    print(f"Pressed key: {args.key}")


def cmd_mount(args):
    host, password = get_connection_info(args)
    payload = {
        "action": "mount",
        "url": args.url,
    }
    resp = make_request(host, "/api/v1/media", payload, password=password)
    print(f"Virtual media mount request sent: {resp}")


def cmd_power(args):
    host, password = get_connection_info(args)
    payload = {
        "action": args.action,
    }
    resp = make_request(host, "/api/v1/power", payload, password=password)
    print(f"Power command '{args.action}' sent: {resp}")


def main():
    parser = argparse.ArgumentParser(description="JetKVM CLI Controller with Frame Diff Detection")
    parser.add_argument("--host", help="JetKVM host URL (e.g. http://192.168.1.100)")
    parser.add_argument("--password", help="JetKVM access password if enabled")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # screenshot
    p_snap = subparsers.add_parser("screenshot", help="Capture snapshot image")
    p_snap.add_argument("--output", "-o", default="screenshot.jpg", help="Output file path")
    p_snap.set_defaults(func=cmd_screenshot)

    # wait-change (intelligent throttling)
    p_wait = subparsers.add_parser("wait-change", help="Wait for screen change or stabilization")
    p_wait.add_argument("--mode", choices=["change", "settle"], default="change",
                        help="'change': wait until screen changes; 'settle': wait until screen stops animating")
    p_wait.add_argument("--threshold", type=float, default=5.0, help="Pixel difference percentage threshold (0-100)")
    p_wait.add_argument("--interval", type=float, default=2.0, help="Polling interval in seconds")
    p_wait.add_argument("--timeout", type=int, default=120, help="Max wait time in seconds")
    p_wait.add_argument("--stable-frames", type=int, default=2, help="Consecutive frames required for 'settle' mode")
    p_wait.add_argument("--output", "-o", help="Save the resulting snapshot image to this path")
    p_wait.set_defaults(func=cmd_wait_change)

    # click
    p_click = subparsers.add_parser("click", help="Send mouse click")
    p_click.add_argument("--x", type=int, required=True, help="Absolute X coordinate")
    p_click.add_argument("--y", type=int, required=True, help="Absolute Y coordinate")
    p_click.add_argument("--button", default="left", choices=["left", "right", "middle"])
    p_click.add_argument("--double", action="store_true", help="Perform double click")
    p_click.set_defaults(func=cmd_click)

    # type
    p_type = subparsers.add_parser("type", help="Type string")
    p_type.add_argument("--text", "-t", required=True, help="Text to type")
    p_type.add_argument("--delay", type=int, default=15, help="Delay between characters in ms")
    p_type.set_defaults(func=cmd_type)

    # press
    p_press = subparsers.add_parser("press", help="Press specific key or shortcut")
    p_press.add_argument("--key", "-k", required=True, help="Key name (e.g. enter, esc, f2, f12)")
    p_press.add_argument("--modifiers", nargs="*", help="Modifier keys (ctrl, alt, shift, win)")
    p_press.set_defaults(func=cmd_press)

    # mount
    p_mount = subparsers.add_parser("mount", help="Mount virtual media ISO")
    p_mount.add_argument("--url", required=True, help="HTTP URL to ISO file")
    p_mount.set_defaults(func=cmd_mount)

    # power
    p_power = subparsers.add_parser("power", help="ATX power control")
    p_power.add_argument("--action", default="short-press", choices=["short-press", "long-press", "reset"])
    p_power.set_defaults(func=cmd_power)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
