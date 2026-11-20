#!/usr/bin/env python3
"""Tiny Govee LAN helper (UDP JSON on ports 4001/4002/4003).

Usage:
  python govee.py scan                     # find lamps on the LAN
  python govee.py on   192.168.50.20       # turn on
  python govee.py off  192.168.50.20       # turn off
  python govee.py bri  192.168.50.20 60    # brightness 1-100
  python govee.py rgb  192.168.50.20 255 128 0
  python govee.py kelv 192.168.50.20 3000
  python govee.py stat 192.168.50.20       # query state
"""
import json
import socket
import sys

SCAN = {"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}


def send(ip, payload, port=4003, wait=True):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(2.0)
    s.sendto(json.dumps(payload).encode(), (ip, port))
    if wait:
        try:
            data, _ = s.recvfrom(4096)
            return json.loads(data.decode("utf-8", "replace"))
        except socket.timeout:
            return None
    return None


def scan():
    found = {}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 4002))
    s.settimeout(0.5)
    m = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    m.sendto(json.dumps(SCAN).encode(), ("239.255.255.250", 4001))
    import time
    end = time.time() + 3
    while time.time() < end:
        try:
            data, addr = s.recvfrom(4096)
            d = json.loads(data.decode("utf-8", "replace")).get("msg", {}).get("data", {})
            key = d.get("device") or addr[0]
            found[key] = {"ip": d.get("ip") or addr[0], "sku": d.get("sku", "?")}
        except socket.timeout:
            m.sendto(json.dumps(SCAN).encode(), ("239.255.255.250", 4001))
    for k, v in found.items():
        print(f"{v['ip']:>16}  {v['sku']:<12} {k}")
    if not found:
        print("no lamps answered (check 'LAN Control' switch in Govee app)")


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    cmd = a[0]
    if cmd == "scan":
        scan()
    elif cmd == "stat":
        print(send(a[1], {"msg": {"cmd": "devStatus", "data": {}}}))
    elif cmd in ("on", "off"):
        send(a[1], {"msg": {"cmd": "turn", "data": {"value": 1 if cmd == "on" else 0}}}, wait=False)
    elif cmd == "bri":
        send(a[1], {"msg": {"cmd": "brightness", "data": {"value": int(a[2])}}}, wait=False)
    elif cmd == "rgb":
        r, g, b = (int(x) for x in a[2:5])
        send(a[1], {"msg": {"cmd": "colorwc", "data": {"color": {"r": r, "g": g, "b": b}, "colorTemInKelvin": 0}}}, wait=False)
    elif cmd == "kelv":
        send(a[1], {"msg": {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": int(a[2])}}}, wait=False)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
