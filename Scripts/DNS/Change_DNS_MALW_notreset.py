import os
import subprocess
import ctypes # Добавлено для корректной работы is_admin на Windows
import argparse
from pathlib import Path
import importlib.util

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

# Проверка наличия прав администратора
def is_admin():
    try:
        # Для Unix-подобных систем (Linux, macOS)
        return os.getuid() == 0
    except AttributeError:
        # Для Windows
        return ctypes.windll.shell32.IsUserAnAdmin() != 0

# Функция изменения DNS IPv4 и DoH
def set_dns(interface, primary_dns, secondary_dns, doh_template):
    print(f"Изменение DNS IPv4 для интерфейса {interface}...")
    try:
        # Настройка IPv4 DNS
        subprocess.run(f'netsh interface ip set dns name="{interface}" static {primary_dns}', check=True, shell=True, capture_output=True, text=True)
        subprocess.run(f'netsh interface ip add dns name="{interface}" {secondary_dns} index=2', check=True, shell=True, capture_output=True, text=True)

        # Настройка DoH
        print("Включение DNS через HTTPS (DoH)...")
        subprocess.run(f'netsh dns add encryption server={primary_dns} dohtemplate={doh_template} autoupgrade=yes', check=True, shell=True, capture_output=True, text=True)
        subprocess.run(f'netsh dns add encryption server={secondary_dns} dohtemplate={doh_template} autoupgrade=yes', check=True, shell=True, capture_output=True, text=True)
        print("DNS IPv4 и DoH успешно изменены!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при изменении DNS IPv4/DoH: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"Непредвиденная ошибка при изменении DNS IPv4/DoH: {e}")
        return False

# Функция возврата настроек по умолчанию (остается здесь, но не используется в __main__)
def reset_dns(interface):
    print(f"Возврат настроек DNS по умолчанию для интерфейса {interface}...")
    try:
        subprocess.run(f'netsh interface ip set dns name="{interface}" dhcp', check=True, shell=True)
        subprocess.run('netsh dns reset', check=True, shell=True) # Сброс специфичных настроек шифрования DNS
        print("Настройки DNS возвращены к значениям по умолчанию!")
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при возврате настроек DNS: {e}")
    except Exception as e:
        print(f"Непредвиденная ошибка при возврате настроек DNS: {e}")

# Функция для очистки кэша DNS
def flush_dns_cache():
    print("Очистка кэша DNS...")
    try:
        subprocess.run('ipconfig /flushdns', check=True, shell=True, capture_output=True, text=True)
        print("Кэш DNS очищен!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при очистке кэша DNS: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False
    except Exception as e:
        print(f"Непредвиденная ошибка при очистке кэша DNS: {e}")
        return False


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
        print("Фоновый контроль split-DNS настроен (проверка раз в минуту).")
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


def _to_bool_env(value):
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


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
    if _to_bool_env(os.getenv("FORCE_DNS_CHANGE")):
        return False, "FORCED_BY_ENV"

    try:
        status = _load_vpn_dns_status(interface_alias)
    except Exception as e:
        print(f"Предупреждение: не удалось проверить VPN/DNS статус: {e}")
        return False, "STATUS_UNKNOWN"

    vpn_active = bool(status.get("VPN_ACTIVE", False))
    proxy_enabled = bool(status.get("PROXY_ENABLED", False))
    hiddify_running = bool(status.get("HIDDIFY_RUNNING", False))

    if vpn_active:
        return True, "VPN_ACTIVE"
    if proxy_enabled:
        return True, "PROXY_ENABLED"
    if hiddify_running:
        return True, "HIDDIFY_RUNNING"
    return False, "DNS_CHANGE_REQUIRED"

# Основной код
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Настройка MALW DNS")
    parser.add_argument("--ipv4")
    parser.add_argument("--ipv6")
    parser.add_argument("--doh")
    parser.add_argument("--interface")
    args = parser.parse_args()
    if not is_admin():
        print("Скрипт требует запуска с правами администратора.")
        print("[DNS_DECISION] changed=false reason=NOT_ADMIN")
        exit(1) # Выход с кодом ошибки, если нет прав администратора

    # Название интерфейса
    interface_name = args.interface or "Ethernet" # Убедитесь, что это правильное имя вашего сетевого интерфейса

    # IPv4 адреса DNS
    primary_dns_ipv4 = "80.253.249.40"
    secondary_dns_ipv4 = "193.23.209.189"

    # DoH шаблон
    if args.ipv4:
        configured_ipv4 = args.ipv4.split(",")
        if len(configured_ipv4) < 2:
            print("Ошибка: --ipv4 должен содержать два адреса через запятую.")
            exit(1)
        primary_dns_ipv4, secondary_dns_ipv4 = configured_ipv4[:2]
    doh_template = args.doh or "https://dns.malw.link/dns-query"

    if not ensure_corporate_split_dns():
        print("[DNS_DECISION] changed=false reason=SPLIT_DNS_FAILED")
        exit(1)

    if not ensure_split_dns_watchdog():
        print("[DNS_DECISION] changed=false reason=SPLIT_DNS_WATCHDOG_FAILED")
        exit(1)

    skip_dns_change, skip_reason = should_skip_dns_change(interface_name)
    if skip_dns_change:
        print(
            "Пропуск изменения DNS: обнаружен активный VPN/Proxy/Hiddify."
        )
        print(f"[DNS_DECISION] changed=false reason={skip_reason}")
        exit(0)

    # Изменение DNS
    print(f"Скрипт: Установка DNS для интерфейса {interface_name}...")
    ipv4_ok = set_dns(interface_name, primary_dns_ipv4, secondary_dns_ipv4, doh_template)
    ipv6_ok = True

    if not (ipv4_ok and ipv6_ok):
        print("Скрипт: DNS изменен не полностью, завершение с ошибкой.")
        print("[DNS_DECISION] changed=false reason=DNS_SET_FAILED")
        exit(1)

    # Очистка кэша DNS после установки новых DNS
    flush_dns_cache()
    corporate_dns_ok = check_corporate_names_resolution()

    if not corporate_dns_ok:
        print(
            "Скрипт: DNS установлен, но корпоративные имена не разрешаются "
            "через системный resolver/NRPT."
        )
        print("[DNS_DECISION] changed=true reason=DNS_SET_CORPORATE_RESOLUTION_FAILED")
        exit(0)

    print("Скрипт: DNS установлен и кэш очищен. Скрипт завершает работу.")
    print("[DNS_DECISION] changed=true reason=DNS_SET")
    # Скрипт завершает свою работу здесь. 
    # Сброс DNS будет выполнен основным скриптом (код3) после завершения его задач.
