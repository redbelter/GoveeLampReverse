# Govee Lamp Reverse Engineering

Notes and helpers for controlling Govee **RGBICW Smart Floor Lamp Basic (H6076)** lamps without the Govee Home app. Verified live over BLE and UDP LAN on two H6076 units.

## TL;DR

- **Wi-Fi/LAN**: plain JSON over UDP — discovery on multicast `239.255.255.250:4001` / listen `4002`, commands unicast to `<lamp-ip>:4003`. Enable *LAN Control* in the Govee app once; after that no app needed.
- **BLE**: GATT service `00010203-0405-0607-0809-0a0b0c0d1910`, write commands to `...2b11`, read/notify status from `...2b10`. Works from ~-85 dB RSSI; at ~-97 dB the link never completes (advertising still heard).

## BLE GATT map (verified)

| Service | Char | Props | Contents |
|---|---|---|---|
| `00001800` Generic Access | `2a00` | read/write | Device name, e.g. `Govee_H6076_503D` |
| | `2a01` | read/write | Appearance `00 00` |
| | `2a04` | read | Preferred params: min 10 ms, max 12.5 ms, latency 0, timeout 4 s (`08 00 0a 00 00 00 90 01`) |
| | `2ac9` | read | empty |
| `00001801` Generic Attribute | `2a05` | indicate/read | Service Changed (`01 00 ff ff`) |
| `00010203-…-0d1910` (Govee control) | `…0d2b10` | notify/read | status channel (`2901` desc: `for gatt Read`) |
| | `…0d2b11` | write, write-no-response, notify/read | command channel (`2901` desc: `for gatt Read`) |
| `02f00000-…-fe00` (Wi-Fi serial bridge) | `ff00` | read | empty |
| | `ff01` | write, write-no-response | write side of serial bridge |
| | `ff02` | notify/read | notify side; static read = `ntf_enable`, notify payload `02 <b> 00 00` echoes first byte written (`2901` desc: `OTA Response`) |
| | `ff03` | read | empty |

Notes:

- Addresses are **random static** (`C5:..`, `D6:..` style). Always resolve by name prefix `Govee_H6076_` (bleak `find_device_by_filter`), and pass `address_type="random"` to `BleakClient`.
- Lamp drops idle connections after ~10 s — use short connect → write → disconnect sessions.
- Commands accepted as JSON (`{"t":1,"p":1}`) *and* as compact binary frames with opcode `0x33` (the app's own scheme). Binary frames below verified end-to-end; one long JSON color frame failed validation with GATT error 13 (`Invalid Attribute Value Length`), so prefer the binary frames or short JSON.
- There is **no microphone service**; the mic is used for sound-reactive effects internally and exposes nothing over GATT.

### Verified binary frames (write to `...2b11`, with-response)

```text
ON            33 01 01
OFF           33 01 00
brightness    33 01 64                  (0x64 = 100 %)
warm orange   33 05 2c 01 01 ff 8c 00 00 00   (RR GG BB + kelvin hi/lo)
```

Segment/section on/off uses the same family: `33 30 <section> 01|00`.

## LAN API (UDP)

Enable *LAN Control* once in the app, then:

```bash
# discover (replies arrive on UDP 4002)
echo -n '{"msg":{"cmd":"scan","data":{"account_topic":"reserve"}}}' | nc -u -w1 239.255.255.250 4001

# control (unicast)
echo -n '{"msg":{"cmd":"turn","data":{"value":0}}}'        | nc -u -w1 192.168.x.x 4003   # off / on=1
echo -n '{"msg":{"cmd":"brightness","data":{"value":60}}}' | nc -u -w1 192.168.x.x 4003   # 1-100 %
echo -n '{"msg":{"cmd":"colorwc","data":{"color":{"r":255,"g":128,"b":0},"colorTemInKelvin":0}}}' | nc -u -w1 192.168.x.x 4003
echo -n '{"msg":{"cmd":"colorwc","data":{"color":{"r":0,"g":0,"b":0},"colorTemInKelvin":3000}}}'  | nc -u -w1 192.168.x.x 4003
echo -n '{"msg":{"cmd":"devStatus","data":{}}}'            | nc -u -w1 192.168.x.x 4003   # reply on 4002
```

`devStatus` reply shape: `{"msg":{"cmd":"devStatus","data":{"onOff":1,"brightness":100,"color":{"r":..,"g":..,"b":..},"colorTemInKelvin":7200}}}`. Per-segment control exists via `ptReal` hex frames.

## Scripts

- `govee.py` — tiny LAN helper: `scan | stat <ip> | on|off <ip> | bri <ip> <n> | rgb <ip> r g b | kelv <ip> <K>`
- `ble_ctl.py` — BLE control demo (connect by name prefix, write verified frames, read status char)

Requires Python with `bleak` for BLE (`py -m pip install bleak`); LAN helper is stdlib-only.

## Community guidance (verified against these lamps)

From `wez/govee-lan-hass`, `wez/govee2mqtt` (FAQ/LAN.md), `homebridge-plugins/homebridge-govee` wiki, `StopBanning/govee-lights`, Govee's official wlan-guide:

- Devices join multicast `239.255.255.250` **only after LAN Control is enabled** — silence on 4001/4003 before the toggle is expected, not a bug. Official fix when the toggle is hidden: power-cycle the lamp, wait ~30 min for the firmware to finish OTA (H6076 needed 1.04.06; a blog with this exact model reported ~1 month), then: kill app → turn phone Wi-Fi OFF → reopen app → device page now shows LAN Control.
- Docker controllers need `network_mode: host` for multicast discovery. Only one LAN controller per host IP (all bind/reply via UDP 4002).
- Replies always go to destination port **4002**, not the sender's ephemeral port — bind a listener on 4002.
- Cross-VLAN/subnet: multicast doesn't cross VLANs; scan by unicast instead (homebridge `lanScanSubnets` CIDR list, `govee2mqtt` `GOVEE_LAN_SCAN=ip1,ip2`). Our `govee.py stat <ip>` is exactly this workaround. Routers may need IGMP snooping enabled for multicast to work at all.
- Connection tier used by mature bridges: LAN → AWS IoT MQTT (undocumented, needs account creds) → Platform API → BLE last. For BLE-only models, StopBanning/govee-lights keeps one persistent BLE connection per lamp, releases it after ~1 min idle so the phone app can still connect; one connection at a time — a connected lamp stops advertising, so scans while another controller holds the link find nothing.
- Segment quirk: per-segment frames set brightness/color only, no independent per-segment power. Some SKUs refuse segment brightness 0.
- Device IDs in Govee logs are supersets of the BLE MAC, not MACs themselves. `"devices not belong you"` from the Platform API = BLE-only device without Wi-Fi support.
- BLE provisioning notes from `gvetk.com`: 2.4 GHz only (no 5 GHz), password travels plaintext, close the vendor app first (one BLE connection at a time), verify join from the network side.

## Bluetooth off/on

Radio state is OS-level: enable/disable via WinRT `Windows.Devices.Radios.Radio` (`set_state_async(On)`), or Settings → Bluetooth. The lamp itself has no per-radio toggle; BLE keeps advertising while connected to Wi-Fi.
