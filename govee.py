#!/usr/bin/env python3
"""Tiny Govee LAN helper (UDP JSON on ports 4001/4002/4003).

Reply quirk (verified on H6076): the lamp unicasts its reply back to our IP
with destination port FIXED at 4002, ignoring the sender's ephemeral port —
so receive on a socket bound to 4002 and send from any ephemeral socket.

Usage:
  py govee.py scan [<ip> ...]            # find lamps (multicast; add IPs to probe by unicast across VLANs)
  py govee.py on   <ip>                  # turn on
  py govee.py off  <ip>                  # turn off
  py govee.py bri  <ip> 60               # brightness 1-100
  py govee.py rgb  <ip> 255 128 0        # set color
  py govee.py kelv <ip> 3000             # set color temperature
  py govee.py stat <ip>                  # query state
"""
import json
import socket
import sys
import time

SCAN = {"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}


def send(ip, payload, port=4003, wait=True):
    """Send one UDP command; collect replies arriving on port 4002."""
    lsn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    lsn.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsn.bind(("0.0.0.0", 4002))
    lsn.settimeout(2.0)
    snd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    reply = None
    try:
        snd.sendto(json.dumps(payload).encode(), (ip, port))
        if wait:
            try:
                data, _ = lsn.recvfrom(4096)
                reply = json.loads(data.decode("utf-8", "replace"))
            except socket.timeout:
                reply = None
    finally:
        lsn.close()
        snd.close()
    return reply


def scan(extra_ips=()):
    found = {}
    lsn = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    lsn.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsn.bind(("0.0.0.0", 4002))
    lsn.settimeout(0.5)
    m = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = json.dumps(SCAN).encode()
    targets = ["239.255.255.250"] + list(extra_ips)
    end = time.time() + 3
    while time.time() < end:
        for tgt in targets:
            try:
                m.sendto(payload, (tgt, 4001))
            except OSError:
                pass
        try:
            while True:
                data, addr = lsn.recvfrom(4096)
                d = json.loads(data.decode("utf-8", "replace")).get("msg", {}).get("data", {})
                key = d.get("device") or addr[0]
                found[key] = {"ip": d.get("ip") or addr[0], "sku": d.get("sku", "?")}
        except socket.timeout:
            pass
    lsn.close()
    m.close()
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
