# -*- coding: utf-8 -*-
# VPN + DNS + Proxy (IPv4) check for Windows

import json
import time
import re
import random
import subprocess, os

def _hidden_si():
    if os.name != "nt":
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0  # SW_HIDE
    return si

def _run_hidden(cmd, timeout=None):
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        shell=False,
        timeout=timeout,
        startupinfo=_hidden_si(),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )






# ===================== Настройки =====================
INTERFACE_ALIAS = "Ethernet"  # при необходимости замени на "Wi-Fi" и т.п.
MAX_TOTAL_SEC   = 6.0
PER_REQ_SEC     = 2.0
# =====================================================

# --------------------- IP / Country ------------------
def get_ip_info():
    try:
        import requests
    except Exception:
        return {"ip": "UNKNOWN", "country": "UNKNOWN", "org": None}

    started = time.monotonic()
    s = requests.Session()
    s.trust_env = False
    headers = {"User-Agent": "vpn-dns-check/1.0"}

    echo_urls = [
        "https://checkip.amazonaws.com",
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://ipinfo.io/ip",
    ]
    random.shuffle(echo_urls)

    geo_urls_tpl = [
        "https://ipapi.co/{ip}/json",
        "http://ip-api.com/json/{ip}?fields=country,org,status,message",
    ]
    random.shuffle(geo_urls_tpl)

    start_with_ipapi = random.choice([True, False])

    if start_with_ipapi:
        try:
            r = s.get("http://ip-api.com/json/?fields=country,query,org,status,message",
                      timeout=PER_REQ_SEC, headers=headers)
            j = r.json()
            if j.get("status") == "success":
                return {
                    "ip": j.get("query") or "UNKNOWN",
                    "country": j.get("country") or "UNKNOWN",
                    "org": j.get("org")
                }
        except Exception:
            pass

    ip = None
    for url in echo_urls:
        if time.monotonic() - started > MAX_TOTAL_SEC:
            break
        try:
            ip_txt = s.get(url, timeout=PER_REQ_SEC, headers=headers).text.strip()
            if ip_txt:
                ip = ip_txt
                break
        except Exception:
            continue

    if ip:
        for tpl in geo_urls_tpl:
            if time.monotonic() - started > MAX_TOTAL_SEC:
                break
            url = tpl.format(ip=ip)
            try:
                j = s.get(url, timeout=PER_REQ_SEC, headers=headers).json()
                country = j.get("country_name") or j.get("country")
                org = j.get("org")
                if j.get("status") == "success" and not country:
                    country = j.get("country")
                    org = j.get("org") or org
                return {"ip": ip, "country": country or "UNKNOWN", "org": org}
            except Exception:
                continue
        return {"ip": ip, "country": "UNKNOWN", "org": None}

    if not start_with_ipapi:
        try:
            r = s.get("http://ip-api.com/json/?fields=country,query,org,status,message",
                      timeout=PER_REQ_SEC, headers=headers)
            j = r.json()
            if j.get("status") == "success":
                return {
                    "ip": j.get("query") or "UNKNOWN",
                    "country": j.get("country") or "UNKNOWN",
                    "org": j.get("org")
                }
        except Exception:
            pass

    return {"ip": "UNKNOWN", "country": "UNKNOWN", "org": None}


# --------------------- DNS helpers -------------------
def _open_reg(path):
    import winreg
    ACCESS = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
    return winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0, ACCESS)

def _guid_from_alias_via_registry(alias):
    import winreg
    base = r"SYSTEM\CurrentControlSet\Control\Network\{4D36E972-E325-11CE-BFC1-08002BE10318}"
    alias_norm = alias.strip().lower()
    try:
        with _open_reg(base) as kbase:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(kbase, i)
                except OSError:
                    break
                i += 1
                try:
                    with _open_reg(base + "\\" + sub + "\\Connection") as kc:
                        try:
                            name = winreg.QueryValueEx(kc, "Name")[0]
                        except FileNotFoundError:
                            name = ""
                        if str(name).strip().lower() == alias_norm:
                            return sub.strip("{}").lower()
                except FileNotFoundError:
                    continue
    except Exception:
        return None
    return None

def _dns_auto_via_netsh(interface_alias):
    try:
        p = _run_hidden(
            ["netsh","interface","ip","show","config", f"name={interface_alias}"],
            timeout=6
        )
        out = p.stdout
        for enc in ("utf-8","cp866","cp1251","latin-1"):
            try:
                text = out.decode(enc, errors="ignore")
                break
            except Exception:
                pass
        else:
            text = out.decode("utf-8", errors="ignore")

        text = text.replace("\xa0"," ")
        if (re.search(r"Статически\s+настроенные\s+DNS", text, re.I) or
            re.search(r"Statically\s+Configured\s+DNS", text, re.I) or
            re.search(r"DNS\s*server\s*assignment\s*:\s*Manual", text, re.I)):
            if re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text) and "Нет" not in text:
                return False
        if (re.search(r"DNS-?серверы\s+с\s+настройкой\s+через\s+DHCP", text, re.I) or
            re.search(r"DNS\s*servers\s*configured\s*through\s*DHCP", text, re.I) or
            re.search(r"DNS\s*server\s*assignment\s*:\s*DHCP", text, re.I)):
            return True
        return True
    except Exception:
        return True

def dns_is_auto_ipv4(interface_alias="Ethernet"):
    guid_norm = _guid_from_alias_via_registry(interface_alias)
    if not guid_norm:
        return _dns_auto_via_netsh(interface_alias)

    import winreg
    base_tcpip = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
    try:
        with _open_reg(base_tcpip) as base:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(base, i)
                except OSError:
                    break
                i += 1
                if sub.strip("{}").lower() != guid_norm:
                    continue
                with _open_reg(base_tcpip + "\\" + sub) as ki:
                    try:
                        name_server = winreg.QueryValueEx(ki, "NameServer")[0]
                    except FileNotFoundError:
                        name_server = ""
                    return not bool(str(name_server).strip())
    except Exception:
        return _dns_auto_via_netsh(interface_alias)

    return True

# --------------------- PROXY check -------------------
def proxy_enabled():
    try:
        import winreg
        path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            enabled = winreg.QueryValueEx(k, "ProxyEnable")[0]
            if enabled:
                try:
                    server = winreg.QueryValueEx(k, "ProxyServer")[0]
                except FileNotFoundError:
                    server = ""
                return True, server
    except Exception:
        pass
    return False, None

def main():
    info = get_ip_info()
    vpn_active = info["country"] not in ("Russia", "RU")
    dns_auto = dns_is_auto_ipv4(INTERFACE_ALIAS)
    proxy_on, proxy_server = proxy_enabled()

    result = {
        **info,
        "VPN_ACTIVE": vpn_active,
        "DNS_AUTO_IPV4": dns_auto,
        "PROXY_ENABLED": proxy_on,
        "PROXY_SERVER": proxy_server,
        "VPN_OR_DNS_ACTIVE": bool(vpn_active or (not dns_auto) or proxy_on),
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nVPN_OR_DNS_ACTIVE = {result['VPN_OR_DNS_ACTIVE']} "
          f"(VPN: {vpn_active}, DNS: {'Auto' if dns_auto else 'Manual'}, "
          f"Proxy: {'ON' if proxy_on else 'OFF'})")


def main_return(interface_alias: str = None):
    alias = interface_alias or INTERFACE_ALIAS
    info = get_ip_info()
    vpn_active = (info.get("country") not in ("Russia", "RU")) and (info.get("country") not in (None, "UNKNOWN"))
    dns_auto = dns_is_auto_ipv4(alias)
    proxy_on, proxy_server = proxy_enabled()
    return {
        **info,
        "VPN_ACTIVE": bool(vpn_active),
        "DNS_AUTO_IPV4": bool(dns_auto),
        "PROXY_ENABLED": proxy_on,
        "PROXY_SERVER": proxy_server,
        "VPN_OR_DNS_ACTIVE": bool(vpn_active or (not dns_auto) or proxy_on),
    }


if __name__ == "__main__":
    main()
