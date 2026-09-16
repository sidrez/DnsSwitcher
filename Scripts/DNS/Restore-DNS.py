# -*- coding: utf-8 -*-
# Reset IPv4/IPv6 DNS to DHCP silently (no new windows), optional DoH reset + flushdns

import sys
import os
import subprocess
import argparse

# --- утилиты ---
def is_admin() -> bool:
    try:
        return os.getuid() == 0  # *nix
    except AttributeError:
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0  # Windows
        except Exception:
            return False

def _decode(data: bytes) -> str:
    if not data:
        return ""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try: return data.decode("utf-16")
        except Exception: pass
    if data.startswith(b"\xef\xbb\xbf"):
        try: return data[3:].decode("utf-8")
        except Exception: pass
    for enc in ("utf-8", "cp866", "cp1251", "latin-1"):
        try: return data.decode(enc)
        except Exception: continue
    return data.decode("utf-8", errors="replace")

def run_hidden(cmd_list):
    startupinfo = None
    creationflags = 0
    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)

    p = subprocess.run(
        cmd_list,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=startupinfo,
        creationflags=creationflags,
        shell=False
    )
    return p.returncode, _decode(p.stdout), _decode(p.stderr)

# --- операции ---
def reset_dns(interface: str):
    print(f"Сброс DNS на автомат для интерфейса: {interface}", flush=True)

    # IPv4 → DHCP
    rc, out, err = run_hidden([
        "netsh", "interface", "ip", "set", "dns",
        f"name={interface}", "dhcp"
    ])
    if out.strip(): print(out, flush=True)
    if rc != 0 or err.strip(): print(err, flush=True)

    # На всякий случай очищаем возможные дополнительные записи IPv4
    run_hidden(["netsh", "interface", "ip", "delete", "dns", f"name={interface}", "all"])

    # IPv6 → DHCP (современный синтаксис)
    rc, out, err = run_hidden([
        "netsh", "interface", "ipv6", "set", "dnsservers",
        f"name={interface}", "source=dhcp"
    ])
    if out.strip(): print(out, flush=True)
    if rc != 0 or err.strip(): print(err, flush=True)

    # Чистим таблицу шифрования DoH (если использовали DoH)
    run_hidden(["netsh", "dns", "reset"])

    print("DNS для IPv4/IPv6 переведены на автоматическое получение (DHCP).", flush=True)

def flush_dns_cache():
    print("Очистка кэша DNS ...", flush=True)
    rc, out, err = run_hidden(["ipconfig", "/flushdns"])
    if out.strip(): print(out, flush=True)
    if rc != 0 or err.strip(): print(err, flush=True)
    print("Кэш DNS очищен.", flush=True)

def main():
    # Не ждём ввода пользователя, просто выполняем сброс
    if hasattr(sys.stdout, "reconfigure"):
        try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

    if not is_admin():
        print("Ошибка: нужны права администратора.", flush=True)
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Сброс DNS на DHCP")
    parser.add_argument("--ipv4")  # Совместимость с единым контрактом запуска GUI.
    parser.add_argument("--ipv6")
    parser.add_argument("--doh")
    parser.add_argument("--interface")
    args = parser.parse_args()
    # Сохраняем совместимость с прежним позиционным именем интерфейса.
    interface = args.interface or "Ethernet"

    reset_dns(interface)
    flush_dns_cache()

if __name__ == "__main__":
    main()
