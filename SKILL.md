---
name: jetkvm-controller
description: Automate PC kitting, BIOS/UEFI setup, and OS installation by controlling JetKVM over network with frame-diff throttling. Use when interacting with JetKVM, capturing PC screens, waiting for installer/progress completion without token waste, sending HID inputs, mounting ISOs, or automating bare-metal computer setup.
---

# JetKVM Controller

Control physical PCs and servers through JetKVM hardware without installing agents on the target machine. Bundles smart frame-difference detection to throttle AI screen polls during long installation/reboot cycles.

## When to Use

- Automating PC kitting (BIOS/UEFI setup, Windows OOBE, Linux installation)
- Throttling snapshot requests during progress bars/install screens via frame-diff analysis
- Capturing screen frames from a target PC connected to JetKVM
- Sending keystrokes, shortcuts (e.g. F2, F12, Win+R), and mouse clicks to bare-metal hardware
- Remotely mounting ISO images via JetKVM Virtual Media and power cycling

## Core Tool: jetkvm_client.py

Set the environment variables or pass `--host`:
```bash
export JETKVM_HOST="http://192.168.1.100"
export JETKVM_PASSWORD="your-password"
```

### 1. Frame-Diff Throttling (Cost & Token Saver)

Instead of calling the AI model continuously while Windows installs or reboots, use `wait-change`:

- **Wait for Screen to Change** (e.g., clicking "Next" and waiting for the next dialog):
  ```bash
  python scripts/jetkvm_client.py wait-change --mode change --threshold 5.0 --timeout 60 -o next_screen.jpg
  ```
- **Wait for Screen to Settle** (e.g., waiting for installation progress bar or spinning dots to finish):
  ```bash
  python scripts/jetkvm_client.py wait-change --mode settle --threshold 1.5 --stable-frames 3 --timeout 300 -o settled_screen.jpg
  ```

### 2. Standard Screen & Input Operations

- **Single Screenshot**:
  ```bash
  python scripts/jetkvm_client.py screenshot --output screen.jpg
  ```
- **Key Press**:
  ```bash
  python scripts/jetkvm_client.py press --key f2
  python scripts/jetkvm_client.py press --key enter
  ```
- **Type Text**:
  ```bash
  python scripts/jetkvm_client.py type --text "Administrator"
  ```
- **Mouse Click**:
  ```bash
  python scripts/jetkvm_client.py click --x 960 --y 540
  ```
- **Virtual Media (ISO Mount)**:
  ```bash
  python scripts/jetkvm_client.py mount --url "http://image-server.local/win11.iso"
  ```
- **Power Control**:
  ```bash
  python scripts/jetkvm_client.py power --action short-press
  ```

## Kitting Flow with Diff Optimization

1. **Trigger Action**: Click "Install Now" or "Next".
2. **Local Throttling**: Run `wait-change --mode settle` to let the OS installer unpack files and settle on the next interactive prompt.
3. **AI Inference**: Send only the final `settled_screen.jpg` to the AI model.
4. **Repeat**: Completely avoids sending dozens of intermediate progress frames to the LLM.
