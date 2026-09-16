# DnsSwitcher

Компактное Windows-приложение для переключения DNS на сетевом интерфейсе `Ethernet` (или интерфейсе, заданном в настройках). Интерфейс запускает проверенные Python-скрипты из `Scripts/DNS`, отображает текущий IPv4 DNS и не дублирует системную логику смены DNS в C#.

## Поддерживаемые DNS

- COMSS;
- Xbox DNS;
- MALW;
- автоматическое получение DNS по DHCP.

## Требования

- Windows;
- .NET 8 Desktop Runtime для запуска опубликованной framework-dependent сборки;
- Python, доступный как `python`, либо путь к `python.exe`, заданный в настройках;
- права администратора.

Установку Python можно проверить командой:

```powershell
python --version
```

## Сборка и запуск

```powershell
dotnet restore
dotnet build -c Release
dotnet publish -c Release -r win-x64 --self-contained false
```

Запустите `DnsSwitcher.exe` из каталога publish. При запуске Windows запросит повышение прав: это необходимо для `netsh`, DoH и настройки DNS-интерфейса.

## providers.json и настройки

Рядом с EXE располагается `providers.json`. В нём хранятся команда Python, имя интерфейса, IPv4/IPv6, DoH, URL проверки и имя скрипта для каждого провайдера. Кнопка «Настройки» позволяет изменить путь Python, интерфейс и DNS-параметры; значения сохраняются в этот файл.

При переключении GUI передаёт копиям Python-скриптов `--ipv4`, `--ipv6`, `--doh`, `--interface`. Без этих аргументов скрипты используют свои первоначальные значения, поэтому их самостоятельный запуск сохраняет прежнее поведение.

## Проверка актуальности IP

Кнопка «Проверить актуальность IP» загружает страницу проверки провайдера с тайм-аутом и User-Agent. Она ищет два IPv4 только внутри блока, связанного со стандартными DNS. Если адреса отличаются, приложение показывает локальные и найденные значения и предлагает обновить их. DoH автоматически не меняется; при нераспознанной странице настройки не изменяются.

## Xbox split-DNS

Логика Xbox DNS полностью находится в `Scripts/DNS/Change_DNS_XBOX_notreset.py`. Она сохраняет split-DNS для зоны `.rgn.ukunistroy.ru`, включая имена `file`, `cde`, `scan`, `base-arc-rgn` и AD SRV-записи. Скрипт использует `Repair_Corporate_Split_DNS.ps1`, state-файл `.Change_DNS_XBOX_notreset_state.json` и watchdog-задачу `Change_DNS_MALW_SplitDNSRepair`, которая периодически восстанавливает NRPT после Group Policy. C#-приложение лишь запускает этот скрипт.

## Сброс DNS

«Сбросить на DHCP» запускает `Restore-DNS.py`: IPv4 и IPv6 переводятся в DHCP, выполняется `netsh dns reset` и очистка DNS-кэша. Эта системная последовательность намеренно не реализована повторно в C#.

## Структура

```text
DnsSwitcher.sln
src/DnsSwitcher/       WinForms-проект, manifest и providers.json
Scripts/DNS/           копии DNS-скриптов и PowerShell-логика split-DNS
Scripts/vpn_dns_check.py  зависимость Xbox/MALW-скриптов
```
