import os
import time
import argparse



def has_ipv6_default_route(interface):
    route = os.popen(
        f'powershell -NoProfile -Command "Get-NetRoute -InterfaceAlias \'{interface}\' '
        '-AddressFamily IPv6 -DestinationPrefix \'::/0\' -ErrorAction SilentlyContinue"'
    ).read()
    return "::/0" in route

# Функция для изменения DNS
def set_dns(interface, dns_ipv4, dns_ipv6, doh_template):
    print(f"Изменение IPv4 DNS для интерфейса {interface}...")
    os.system(f'netsh interface ip set dns name="{interface}" static {dns_ipv4[0]}')
    for index, dns_server in enumerate(dns_ipv4[1:], start=2):
        os.system(f'netsh interface ip add dns name="{interface}" {dns_server} index={index}')

    # Включение DNS через HTTPS (DoH)
    print("Включение DNS через HTTPS (DoH)...")
    for dns_server in dns_ipv4:
        os.system(f'netsh dns add encryption server={dns_server} dohtemplate={doh_template} autoupgrade=yes')

    if has_ipv6_default_route(interface):
        print(f"Изменение IPv6 DNS для интерфейса {interface}...")
        os.system(f'netsh interface ipv6 set dnsservers name="{interface}" static {dns_ipv6[0]} primary')
        for index, dns_server in enumerate(dns_ipv6[1:], start=2):
            os.system(f'netsh interface ipv6 add dnsservers name="{interface}" {dns_server} index={index}')
    else:
        print("IPv6 default route отсутствует — IPv6 DNS не задаём.")
        os.system(f'netsh interface ipv6 set dnsservers name="{interface}" source=dhcp')

    print("DNS успешно изменен!")

# Функция для возврата настроек по умолчанию
def reset_dns(interface):
    print(f"Возврат настроек DNS по умолчанию для интерфейса {interface}...")
    os.system(f'netsh interface ip set dns name="{interface}" dhcp')
    os.system(f'netsh interface ip delete dns name="{interface}" all')
    os.system(f'netsh interface ipv6 set dnsservers name="{interface}" source=dhcp')
    os.system(f'netsh dns reset')
    print("Настройки DNS возвращены к значениям по умолчанию!")

# Функция для очистки кэша DNS
def flush_dns_cache():
    print("Очистка кэша DNS...")
    os.system('ipconfig /flushdns')
    print("Кэш DNS очищен!")

# Основной код
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Настройка COMSS DNS")
    parser.add_argument("--ipv4")
    parser.add_argument("--ipv6")
    parser.add_argument("--doh")
    parser.add_argument("--interface")
    args = parser.parse_args()
    # Название интерфейса
    interface_name = args.interface or "Ethernet"

    # Comss.one DNS по https://www.comss.ru/page.php?id=7315
    dns_ipv4 = [
        "83.220.169.155",
        "212.109.195.93",
    ]
    dns_ipv6 = [
        "2a01:230:4:915::2",
        "2a03:6f00:a::3f24",
    ]

    # DoH шаблон
    doh_template = args.doh or "https://dns.comss.one/dns-query"
    dns_ipv4 = args.ipv4.split(",") if args.ipv4 else dns_ipv4
    dns_ipv6 = args.ipv6.split(",") if args.ipv6 else dns_ipv6

    # Изменение DNS
    set_dns(interface_name, dns_ipv4, dns_ipv6, doh_template)

##    try:
##        # Ожидание подтверждения
##        print("DNS изменен. Нажмите Enter, чтобы вернуть настройки по умолчанию...")
##        input()  # Ожидание нажатия Enter
##    except KeyboardInterrupt:
##        print("\nОперация отменена пользователем.")
##
##    # Возврат настроек по умолчанию
##    reset_dns(interface_name)
   
    # Очистка кэша DNS
    flush_dns_cache()
