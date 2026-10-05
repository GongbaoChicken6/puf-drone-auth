# 433MHz Radio Module

## Wiring (to be completed W2)

| Radio Pin | Connects to | Notes |
|---|---|---|
| TX | FPGA RX (via header) | 3.3V TTL |
| RX | FPGA TX (via header) | 3.3V TTL |
| GND | GND | Common ground required |
| VCC | 5V | From board 5V pin |

## Configuration (SiK AT commands)
```
AT+BAUD=57600    # Serial baud rate
AT+AIR=64        # Air data rate (kbps)
AT+ECC=ON        # Error correction
AT+NETID=0x42    # Network ID (both radios must match)
```

## Compliance
- 433.05~434.79 MHz (10mW e.r.p.) per MIIT 2019 No.52
- Do NOT use 915MHz (not approved in China)
