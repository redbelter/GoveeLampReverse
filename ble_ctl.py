#!/usr/bin/env python3
"""BLE control demo for Govee H6076 floor lamps (bleak).

Usage:
  py ble_ctl.py              # toggle: on -> bright -> warm orange -> off
  py ble_ctl.py on|off|bri N|rgb R G B   # single command

Addresses are random-static, so the script resolves by name prefix.
"""
import asyncio
import sys

from bleak import BleakClient, BleakScanner

NAME_PREFIX = "Govee_H6076"
CH_STATUS = "00010203-0405-0607-0809-0a0b0c0d2b10"   # notify/read
CH_WRITE = "00010203-0405-0607-0809-0a0b0c0d2b11"    # write


def on():      return [0x33, 0x01, 0x01]
def off():     return [0x33, 0x01, 0x00]
def bri(n):    return [0x33, 0x01, max(1, min(100, int(n)))]
def rgb(r, g, b):  # warm-white channel off via kelvin hi/lo = 00 00
    return [0x33, 0x05, 0x2C, 0x01, 0x01, int(r), int(g), int(b), 0x00, 0x00]


async def run(frames):
    dev = None
    last_err = None
    for attempt in range(4):
        if dev is None:
            dev = await BleakScanner.find_device_by_filter(
                lambda d, a: (getattr(d, "name", None)
                              or getattr(a, "local_name", None) or "").startswith(NAME_PREFIX),
                timeout=8)
            if dev is None:
                print("no Govee lamp found")
                return
        c = BleakClient(dev.address, timeout=30, address_type="random")
        try:
            await c.connect()
        except Exception as e:
            last_err = e
            dev = None  # address may have rotated; re-discover
            await asyncio.sleep(1)
            continue
        print(f"connected {dev.address} ({dev.name}) [try {attempt + 1}]")
        break
    else:
        print(f"connect failed: {last_err}")
        return
    for f in frames:
        await c.write_gatt_char(CH_WRITE, bytearray(f), response=True)
        await asyncio.sleep(0.5)
    try:
        val = await c.read_gatt_char(CH_STATUS)
        print("status:", bytes(val).hex() or "(empty)")
    except Exception:
        pass
    await c.disconnect()


def main():
    a = sys.argv[1:]
    if not a:
        frames = [on(), bri(100), rgb(255, 140, 0), off()]
    elif a[0] == "on":
        frames = [on()]
    elif a[0] == "off":
        frames = [off()]
    elif a[0] == "bri":
        frames = [bri(a[1])]
    elif a[0] == "rgb":
        frames = [rgb(*a[1:4])]
    else:
        print(__doc__)
        return
    asyncio.run(run(frames))


if __name__ == "__main__":
    main()
