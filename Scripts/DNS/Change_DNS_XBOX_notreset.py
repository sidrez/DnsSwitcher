# Источники:
# - https://vc.ru/ai/2706741-kak-ispolzovat-gemini-chatgpt-i-notion-bez-vpn
# - https://xbox-dns.ru/#setup
import ctypes
import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


INTERFACE_NAME = "Ethernet"
STATE_FILE = Path(__file__).with_name(".Change_DNS_XBOX_notreset_state.json")
CORPORATE_DNS_NAMESPACE = ".rgn.ukunistroy.ru"
CORPORATE_DNS_SERVERS = ("10.0.1.120", "10.0.1.186")
CORPORATE_DNS_NAMES = (
    "file.rgn.ukunistroy.ru",
    "cde.rgn.ukunistroy.ru",
    "scan.rgn.ukunistroy.ru",
    "base-arc-rgn.rgn.ukunistroy.ru",
)
CORPORATE_AD_SRV_NAMES = (
    "_ldap._tcp.dc._msdcs.rgn.ukunistroy.ru",
    "_kerberos._tcp.rgn.ukunistroy.ru",
)
SPLIT_DNS_REPAIR_SCRIPT = Path(__file__).with_name("Repair_Corporate_Split_DNS.ps1")
SPLIT_DNS_INSTALL_DIR = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Change_DNS_MALW"
SPLIT_DNS_INSTALLED_SCRIPT = SPLIT_DNS_INSTALL_DIR / SPLIT_DNS_REPAIR_SCRIPT.name
SPLIT_DNS_WATCHDOG_TASK = "Change_DNS_MALW_SplitDNSRepair"

PROVIDERS = {
    "vc": {
        "label": "vc.ru / XBox DNS",
        "source": "https://vc.ru/ai/2706741-kak-ispolzovat-gemini-chatgpt-i-notion-bez-vpn",
        "next": "xbox",
        "ipv4": ["176.99.11.77", "80.78.247.254"],
        "ipv6": [],
        "doh_template": "https://xbox-dns.ru/dns-query",
    },
    "xbox": {
        "label": "xbox-dns.ru",
        "source": "https://xbox-dns.ru/#setup",
        "next": "vc",
        "ipv4": ["111.88.96.50", "111.88.96.51"],
        "ipv6": ["2a00:ab00:1233:26::50", "2a00:ab00:1233:26::51"],
        "doh_template": "https://xbox-dns.ru/dns-query",
    },
}


def is_admin():
    try:
        return os.getuid() == 0
    except AttributeError:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False


def run_hidden(cmd_list, check=True):
    startupinfo = None
    creationflags = 0
    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)

    result = subprocess.run(
        cmd_list,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        startupinfo=startupinfo,
        creationflags=creationflags,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            cmd_list,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def _load_vpn_dns_status(interface_alias):
    check_script = Path(__file__).resolve().parents[1] / "vpn_dns_check.py"
    if not check_script.is_file():
        raise FileNotFoundError(f"vpn_dns_check.py not found: {check_script}")

    spec = importlib.util.spec_from_file_location("vpn_dns_check", str(check_script))
    if not spec or not spec.loader:
        raise ImportError("Не удалось загрузить спецификацию vpn_dns_check.py")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    if not hasattr(module, "main_return"):
        raise AttributeError("В vpn_dns_check.py отсутствует main_return().")
    return module.main_return(interface_alias)


def should_skip_dns_change(interface_alias):
    if str(os.getenv("FORCE_DNS_CHANGE") or "").strip().lower() in ("1", "true", "yes", "on"):
        return False, "FORCED_BY_ENV"

    try:
        status = _load_vpn_dns_status(interface_alias)
    except Exception as e:
        print(f"Предупреждение: не удалось проверить VPN/DNS статус: {e}")
        return False, "STATUS_UNKNOWN"

    if bool(status.get("VPN_ACTIVE", False)):
        return True, "VPN_ACTIVE"
    if bool(status.get("PROXY_ENABLED", False)):
        return True, "PROXY_ENABLED"
    if bool(status.get("HIDDIFY_RUNNING", False)):
        return True, "HIDDIFY_RUNNING"
    return False, "DNS_CHANGE_REQUIRED"


def has_ipv6_default_route(interface):
    result = run_hidden(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-NetRoute "
                f"-InterfaceAlias '{interface}' "
                "-AddressFamily IPv6 "
                "-DestinationPrefix '::/0' "
                "-ErrorAction SilentlyContinue"
            ),
        ],
        check=False,
    )
    return "::/0" in (result.stdout or "")


def load_provider_key():
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        key = data.get("next_provider")
        if key in PROVIDERS:
            return key
    except Exception:
        pass
    return "xbox"


def save_next_provider(provider_key):
    next_key = PROVIDERS[provider_key]["next"]
    STATE_FILE.write_text(
        json.dumps({"next_provider": next_key}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return next_key


def set_dns_ipv4(interface, dns_servers, doh_template):
    print(f"Изменение IPv4 DNS для интерфейса {interface}...")
    run_hidden(["netsh", "interface", "ip", "set", "dns", f"name={interface}", "static", dns_servers[0]])
    for index, dns_server in enumerate(dns_servers[1:], start=2):
        run_hidden(["netsh", "interface", "ip", "add", "dns", f"name={interface}", dns_server, f"index={index}"])

    print("Включение DNS через HTTPS (DoH)...")
    for dns_server in dns_servers:
        run_hidden(
            [
                "netsh",
                "dns",
                "add",
                "encryption",
                f"server={dns_server}",
                f"dohtemplate={doh_template}",
                "autoupgrade=yes",
            ],
            check=False,
        )
    print("IPv4 DNS и DoH применены.")


def set_dns_ipv6(interface, dns_servers):
    if not dns_servers:
        print("Для выбранного профиля IPv6 DNS не указан — IPv6 DNS переводим в DHCP.")
        run_hidden(["netsh", "interface", "ipv6", "set", "dnsservers", f"name={interface}", "source=dhcp"], check=False)
        return

    if not has_ipv6_default_route(interface):
        print("IPv6 default route отсутствует — IPv6 DNS не задаём.")
        run_hidden(["netsh", "interface", "ipv6", "set", "dnsservers", f"name={interface}", "source=dhcp"], check=False)
        return

    print(f"Изменение IPv6 DNS для интерфейса {interface}...")
    run_hidden(["netsh", "interface", "ipv6", "set", "dnsservers", f"name={interface}", "static", dns_servers[0], "primary"])
    for index, dns_server in enumerate(dns_servers[1:], start=2):
        run_hidden(["netsh", "interface", "ipv6", "add", "dnsservers", f"name={interface}", dns_server, f"index={index}"])
    print("IPv6 DNS применены.")


def flush_dns_cache():
    print("Очистка кэша DNS...")
    run_hidden(["ipconfig", "/flushdns"], check=False)
    print("Кэш DNS очищен.")


def ensure_corporate_split_dns():
    # NRPT нужен, чтобы *.rgn.ukunistroy.ru резолвились через корпоративные DNS,
    # даже когда основной DNS на Ethernet заменен на внешний DNS/DoH.
    print(
        "Настройка split-DNS NRPT: "
        f"{CORPORATE_DNS_NAMESPACE} -> {', '.join(CORPORATE_DNS_SERVERS)}..."
    )
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SPLIT_DNS_REPAIR_SCRIPT),
            ],
            check=True,
            capture_output=True,
            text=True,
            errors="ignore",
        )
        print("Split-DNS NRPT успешно настроен.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при настройке split-DNS NRPT: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"Непредвиденная ошибка при настройке split-DNS NRPT: {e}")
        return False


def ensure_split_dns_watchdog():
    print("Настройка фонового контроля корпоративного split-DNS...")
    source_path = str(SPLIT_DNS_REPAIR_SCRIPT).replace("'", "''")
    install_dir = str(SPLIT_DNS_INSTALL_DIR).replace("'", "''")
    installed_path = str(SPLIT_DNS_INSTALLED_SCRIPT).replace("'", "''")
    task_name = SPLIT_DNS_WATCHDOG_TASK.replace("'", "''")
    command = (
        "$ErrorActionPreference = 'Stop'; "
        f"New-Item -ItemType Directory -Path '{install_dir}' -Force | Out-Null; "
        f"Copy-Item -LiteralPath '{source_path}' -Destination '{installed_path}' -Force; "
        f"& icacls.exe '{install_dir}' /inheritance:r "
        "/grant:r '*S-1-5-18:(OI)(CI)(F)' "
        "'*S-1-5-32-544:(OI)(CI)(F)' "
        "'*S-1-5-32-545:(OI)(CI)(RX)' | Out-Null; "
        "if ($LASTEXITCODE -ne 0) { throw 'Failed to secure watchdog directory ACL' }; "
        f"$arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"{installed_path}\"'; "
        "$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments; "
        "$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) "
        "-RepetitionInterval (New-TimeSpan -Minutes 5); "
        "$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' "
        "-LogonType ServiceAccount -RunLevel Highest; "
        "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable "
        "-ExecutionTimeLimit (New-TimeSpan -Minutes 1) "
        "-MultipleInstances IgnoreNew -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries; "
        f"Register-ScheduledTask -TaskName '{task_name}' -Action $action "
        "-Trigger $trigger -Principal $principal -Settings $settings "
        "-Description 'Восстанавливает split-DNS после обновления Group Policy' "
        "-Force | Out-Null"
    )

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            check=True,
            capture_output=True,
            text=True,
            errors="ignore",
        )
        print("Фоновый контроль split-DNS настроен (проверка раз в 5 минут).")
        return True
    except subprocess.CalledProcessError as e:
        print("Не удалось настроить фоновый контроль split-DNS.")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"Непредвиденная ошибка при настройке фонового контроля split-DNS: {e}")
        return False


def check_corporate_names_resolution():
    print("Проверка корпоративных SMB-имён и AD SRV-записей...")
    names = ",".join(f'"{name}"' for name in CORPORATE_DNS_NAMES)
    srv_names = ",".join(f'"{name}"' for name in CORPORATE_AD_SRV_NAMES)
    servers = ",".join(f'"{server}"' for server in CORPORATE_DNS_SERVERS)
    command = (
        "$failed = @(); "
        f"foreach ($name in @({names})) {{ "
        "try { Resolve-DnsName -Name $name -Type A -ErrorAction Stop | Out-Null } "
        "catch { $failed += ('A:' + $name) } "
        "}; "
        f"foreach ($name in @({srv_names})) {{ "
        "try { "
        "$records = @(Resolve-DnsName -Name $name -Type SRV -ErrorAction Stop | "
        "Where-Object Type -eq 'SRV'); "
        "if ($records.Count -eq 0) { throw 'No SRV records' }; "
        "foreach ($target in @($records.NameTarget | Sort-Object -Unique)) { "
        "Resolve-DnsName -Name $target -Type A -ErrorAction Stop | Out-Null "
        "} "
        "} catch { $failed += ('SRV:' + $name) } "
        "}; "
        "if ($failed.Count -gt 0) { "
        "Write-Error ('Failed corporate DNS checks: ' + ($failed -join ', ')); "
        f"foreach ($server in @({servers})) {{ "
        f"foreach ($name in @({names})) {{ "
        "try { "
        "$result = Resolve-DnsName -Name $name -Type A -Server $server -ErrorAction Stop; "
        "$ips = ($result | Where-Object IPAddress | Select-Object -ExpandProperty IPAddress) -join ','; "
        "Write-Output ('Direct corporate DNS OK: ' + $server + ' ' + $name + ' ' + $ips) "
        "} catch { "
        "Write-Output ('Direct corporate DNS FAIL: ' + $server + ' ' + $name + ' ' + $_.Exception.Message) "
        "} "
        "} "
        f"foreach ($name in @({srv_names})) {{ "
        "try { "
        "$targets = (Resolve-DnsName -Name $name -Type SRV -Server $server -ErrorAction Stop | "
        "Where-Object Type -eq 'SRV' | Select-Object -ExpandProperty NameTarget) -join ','; "
        "Write-Output ('Direct corporate SRV OK: ' + $server + ' ' + $name + ' ' + $targets) "
        "} catch { "
        "Write-Output ('Direct corporate SRV FAIL: ' + $server + ' ' + $name + ' ' + $_.Exception.Message) "
        "} "
        "} "
        "} "
        "exit 1 "
        "}"
    )

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            check=True,
            capture_output=True,
            text=True,
            errors="ignore",
        )
        print("Корпоративные SMB-имена и AD SRV-записи успешно разрешаются.")
        return True
    except subprocess.CalledProcessError as e:
        print("Предупреждение: корпоративные DNS-имена не разрешаются.")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        print("[DNS_WARNING] corporate_names_resolution_failed")
        return False
    except Exception as e:
        print(f"Непредвиденная ошибка при проверке корпоративных DNS-имен: {e}")
        print("[DNS_WARNING] corporate_names_resolution_failed")
        return False


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if not is_admin():
        print("Скрипт требует запуска с правами администратора.")
        print("[DNS_DECISION] changed=false reason=NOT_ADMIN")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Настройка Xbox DNS")
    parser.add_argument("--ipv4")
    parser.add_argument("--ipv6")
    parser.add_argument("--doh")
    parser.add_argument("--interface")
    args = parser.parse_args()
    interface_name = args.interface or INTERFACE_NAME

    if not ensure_corporate_split_dns():
        print("[DNS_DECISION] changed=false reason=SPLIT_DNS_FAILED")
        sys.exit(1)

    if not ensure_split_dns_watchdog():
        print("[DNS_DECISION] changed=false reason=SPLIT_DNS_WATCHDOG_FAILED")
        sys.exit(1)

    skip_dns_change, skip_reason = should_skip_dns_change(interface_name)
    if skip_dns_change:
        print("Пропуск изменения DNS: обнаружен активный VPN.")
        print(f"[DNS_DECISION] changed=false reason={skip_reason}")
        sys.exit(0)

    provider_key = load_provider_key()
    provider = dict(PROVIDERS[provider_key])
    if args.ipv4:
        provider["ipv4"] = args.ipv4.split(",")
    if args.ipv6 is not None:
        provider["ipv6"] = [item for item in args.ipv6.split(",") if item]
    if args.doh:
        provider["doh_template"] = args.doh
    print(f"Профиль XBox DNS: {provider['label']}")
    print(f"Источник: {provider['source']}")

    try:
        set_dns_ipv4(interface_name, provider["ipv4"], provider["doh_template"])
        set_dns_ipv6(interface_name, provider["ipv6"])
        flush_dns_cache()
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при изменении DNS: {e}")
        print(f"Stdout: {e.output}")
        print(f"Stderr: {e.stderr}")
        print("[DNS_DECISION] changed=false reason=DNS_SET_FAILED")
        sys.exit(1)
    except Exception as e:
        print(f"Непредвиденная ошибка при изменении DNS: {e}")
        print("[DNS_DECISION] changed=false reason=DNS_SET_FAILED")
        sys.exit(1)

    corporate_dns_ok = check_corporate_names_resolution()

    next_key = save_next_provider(provider_key)
    print(f"DNS установлен. Следующий клик применит профиль: {PROVIDERS[next_key]['label']}")
    if not corporate_dns_ok:
        print(
            "DNS установлен, но корпоративные имена не разрешаются "
            "через системный resolver/NRPT."
        )
        print(
            f"[DNS_DECISION] changed=true reason=DNS_SET_CORPORATE_RESOLUTION_FAILED "
            f"provider={provider_key} next={next_key}"
        )
        return
    print(f"[DNS_DECISION] changed=true reason=DNS_SET provider={provider_key} next={next_key}")


if __name__ == "__main__":
    main()
