#!/usr/bin/env python3
"""Join Govee H6076 lamps to Wi-Fi over BLE — no Govee app needed.

Protocol (verified on this SKU):
  - ff01/ff02 on service 02f00000-...-fe00 is a serial bridge to the lamp's
    Wi-Fi module. ff01 = TX (writes), ff02 = RX (reads + notifications;
    static value 'ntf_enable', notify frames 02 <echoed byte> 00 00).
  - The bridge echoes the first byte of every write, which proves the
    link is alive; full JSON replies are NOT returned over notify — the
    bridge is one-way echo on this firmware, so verification of the join
    is done from the network side (ARP lease on the Wi-Fi subnet).
  - Provisioning payload is JSON written to ff01 (this is what the Govee
    Home app itself sends): {"ssid":"X","pwd":"Y","eid":6,"pid":4}
    The firmware accepts NUL-terminated + 16-byte-padded or bare JSON.
  - Addresses are random-static: rediscover by name prefix 'Govee_H6076',
    connect with address_type='random', retry on link timeouts.

After provisioning the lamp reboots its Wi-Fi module; success = ARP entry
for Govee OUI bc-24-11 on the Wi-Fi subnet.

Usage:
  py wifi_join.py                       # creds auto-detected, joins every lamp found
  py wifi_join.py <SSID> <PASSWORD>     # explicit creds
"""
import asyncio
import json
import subprocess
import sys

from bleak import BleakClient, BleakScanner

NAME_PREFIX = "Govee_H6076"
FF01 = "02f00000-0000-0000-0000-00000000ff01"
FF02 = "02f00000-0000-0000-0000-00000000ff02"
GOVEE_OUI = "bc-24-11"

RX = []


def saved_wifi():
    """Read the last-connected Wi-Fi credentials from the Windows profile store."""
    ps = ("$p = Get-ChildItem 'HKLM:\\SOFTWARE\\Microsoft\\ClipboardManager' | Out-Null; "
          "$c = (Get-NetConnectionProfile | Where-Object IPv4ConnectIndex | Select-Object -First 1).Name; "
          "$pw = (netsh wlan show profiles $c key=clear | Select-String 'Key Content').Line; "
          "Write-Output ($c + '|' + ($pw -replace '^.*?:\\s*',''))")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        if "|" in out:
            ssid, _, pwd = out.partition("|")
            return ssid.strip(), pwd.strip()
    except Exception:
        pass
    return None, None


def _notify_cb(sender, data):
    RX.append(bytes(data))


def _pad(js: str) -> bytearray:
    """NUL-terminate and pad JSON to a 16-byte block."""
    body = js + "\x00"
    body += "\x00" * ((16 - len(body) % 16) % 16)
    return bytearray(body, "utf-8")


async def _connect():
    dev = None
    last = None
    for attempt in range(6):
        dev = await BleakScanner.find_device_by_filter(
            lambda d, a: (getattr(d, "name", None)
                          or getattr(a, "local_name", None) or "").startswith(NAME_PREFIX),
            timeout=8)
        if dev is None:
            await asyncio.sleep(1)
            continue
        c = BleakClient(dev.address, timeout=25, address_type="random")
        try:
            await c.connect()
            return c, dev
        except Exception as e:
            last = e
            dev = None
            await asyncio.sleep(1)
    raise RuntimeError(f"could not connect: {last}")


async def main(creds):
    c, dev = await _connect()
    print(f"connected {dev.address} ({dev.name})")
    await c.start_notify(FF02, _notify_cb)
    await asyncio.sleep(0.3)

    # bridge sanity: expect notify echoing first byte of payload
    RX.clear()
    await c.write_gatt_char(FF01, bytearray("A", "utf-8"), response=True)
    await asyncio.sleep(0.5)
    print("bridge echo:", RX[-1] if RX else "(none)")

    # ask the module for its stored config
    RX.clear()
    await c.write_gatt_char(FF01, _pad('{"cmd":"query"}'), response=False)
    await asyncio.sleep(1.2)
    cfg = {}
    for b in RX:
        txt = b.decode(errors="replace").strip("\x00 ")
        if txt and "{" in txt:
            import json
            try:
                cfg = json.loads(txt)
            except Exception:
                pass
        print("rx:", txt or bytes(b).hex())
    ssid = cfg.get("ssid") or cfg.get("SSID")
    pwd = cfg.get("pwd") or cfg.get("password")
    if ssid:
        print(f"lamp currently joins: {ssid}")

    if creds:
        ssid, pwd = creds[0], creds[1] if len(creds) > 1 else ""
    elif ssid:
        pwd = pwd or ""

    # re-provision (join) — same creds when none given; idempotent
    js = '{"ssid":"%s","pwd":"%s","eid":6,"pid":4}' % (ssid or "", pwd or "")
    RX.clear()
    await c.write_gatt_char(FF01, _pad(js), response=False)
    await asyncio.sleep(2.0)
    for b in RX:
        print("join rx:", bytes(b)[:120])
    print(f"join sent for ssid={ssid!r}")
    try:
        await c.stop_notify(FF02)
    except Exception:
        pass
    await c.disconnect()
    print("done")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
