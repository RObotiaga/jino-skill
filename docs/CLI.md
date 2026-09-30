# Jino CLI

## Запуск и вход

`jino ...` после `pip install .`, `python -m jino_domains_sdk ...`, либо установленный launcher skill:

```powershell
$jino = Join-Path $env:USERPROFILE '.codex/skills/jino-control/scripts/jino.ps1'
& $jino status
& $jino auth configure
& $jino auth check --domain example.com
```

`auth configure` запускает сам пользователь в интерактивном терминале. Пароль скрыт при вводе. Профиль `%LOCALAPPDATA%/JinoCLI/credentials.dpapi` шифруется Windows DPAPI для текущего Windows пользователя. `auth clear` удаляет только сохранённый профиль. При наличии переменных среды `JINO_LOGIN` / `JINO_PASSWORD` используются они; нужно задать обе. Cookies и access-token остаются в памяти отдельного вызова CLI. Каждый новый вызов выполняет автоматический HTTP-вход заново, без фонового процесса и браузера.

При отсутствии runtime выполните `scripts/install.ps1 -Source <папка SDK>`. Скрипт создаёт отдельный venv в папке skill и устанавливает SDK обычной копией, без editable-ссылки. Для обновления SDK повторите установку. Исходный SDK понадобится только для переустановки.

## Команды

| Команда | Назначение |
| --- | --- |
| `status` | Локальная конфигурация, версия и границы подтверждённости |
| `auth configure/check/clear` | Сохранить зашифрованный профиль / проверить вход / удалить профиль |
| `domains list/add DOMAIN` | Домены аккаунта / добавить существующий домен |
| `domain show/renewal/nameservers DOMAIN` | Настройки, сведения о продлении, NS |
| `dns list DOMAIN` | Записи, типы, имена, ID, значения и возможность изменения |
| `dns add/update DOMAIN` | Создать или изменить запись, поля задаются флагами |
| `dns ip DOMAIN --record-id N --ip IP` | Изменить IP A/AAAA с сохранением имени и типа |
| `dns delete DOMAIN --record-id N` | Удалить одну запись |
| `dns reset DOMAIN` | Сбросить всю зону; для выполнения нужен `--confirm-domain DOMAIN` |
| `settings get/set DOMAIN` | Чтение / WWW, IPv6, NS |
| `contacts get/update DOMAIN` | Группы контактов / обновление через JSON-файл |
| `ssl get/request/upload/delete DOMAIN` | Сертификат, заявка, загрузка PEM, удаление |
| `https set DOMAIN --enabled on/off` | Принудительный HTTPS |
| `subdomain add DOMAIN --name api` | Добавить поддомен |

Точный синтаксис — `<команда> --help`. Подкоманды изменения принимают `--apply`; без него возвращают план и не отправляют мутацию. План может делать запросы чтения и входа. `auth configure/clear` — локальные операции, применяются сразу.

## Типичные действия

```powershell
& $jino domains list --limit 20 --filter example
& $jino dns list example.com --type A --name api
& $jino dns ip example.com --record-id 123 --ip 203.0.113.42 --expected-value 203.0.113.10 --apply
& $jino dns add example.com --type TXT --name _acme-challenge --txt 'verification' --apply
& $jino dns update example.com --record-id 234 --type MX --mx mail.example.com --priority 10 --apply
& $jino settings set example.com --ipv6 on --apply
& $jino settings set example.com --nameserver ns1.example.net --nameserver ns2.example.net --apply
& $jino ssl upload example.com --cert-file C:\secure\cert.pem --key-file C:\secure\key.pem --apply
```

ID выбирается из записей нужного домена. Имя `@` означает корень. При `dns update` отсутствие `--name` сохраняет имя. Для редактирования сложных типов нужно передать все поля: старые структурированные поля отсутствуют в read-query. NAPTR и SSHFP доступны только для добавления. Для SRV имя задаётся `--service`, флаг `--name` не принимается. Для NAPTR flags — строка; для CAA — число. TXT/SPF/CAA используют исходное browser btoa, допускающее Latin-1.

Контакты по умолчанию возвращают только названия групп; `--full` выводит полные контактные данные. `contacts update --type ... --file ...` читает объект JSON; тип и схема берутся из текущего ответа Jino. SSL принимает локальные PEM-файлы, не выводит их содержимое. Пароль ключа задаётся переменной среды, имя передаётся через `--password-env`.

## JSON и результат записи

Успешное чтение/план/подтверждённое изменение: `{"ok":true,"data":...}`.
Ошибка: `{"ok":false,"error":{"code":"...","message":"..."}}`.
Результаты записей различаются:

- `outcome=planned`: мутация не отправлялась.
- `outcome=applied`, `verification=read_back`: независимое чтение подтвердило состояние. Поддерживается для A/AAAA, удаления записи, добавления домена/поддомена, HTTPS и настроек при известных полях ответа.
- `RESULT_UNVERIFIED`, код 6: HTTP-запрос завершён, но полное соответствие результата не доказано. Сейчас так завершаются сложные DNS, reset, контакты и SSL; выполните отдельное чтение перед дальнейшим решением.
- `WRITE_RESULT_UNKNOWN`, код 6: запрос или последующее чтение оборвались; действие могло примениться. Автоматический повтор отсутствует.
- `PARTIAL_UPDATE`, код 6: изменение настроек остановилось на одном из шагов; `steps` показывает завершённые запросы, не попытанные и неопределённый шаг. `request_completed` не означает доказанное применение.

`--expected-value` проверяет чтение перед мутацией, но не является серверным compare-and-swap. Другой процесс может изменить зону между чтением и записью. Подтверждение состояния не означает завершение распространения DNS или выпуска SSL.

Коды выхода: 0 — результат чтения/план/подтверждение; 2 — аргументы или файл; 3 — вход; 4 — объект недоступен или запись защищена; 5 — запрос/протокол; 6 — результат записи не подтверждён/частичный; 130 — прерывание. Сетевые ошибки при `--apply` трактуются осторожно как неизвестный результат, даже если сбой произошёл до отправки мутации.

## Подтверждённость

CLI использует HTTP SDK; Selenium, Playwright, Puppeteer не применяются. HTTP-авторизация по сохранённым учётным данным и чтение доменов/DNS/настроек/NS/SSL проверены на реальном аккаунте. Исправлена цепочка перенаправлений через `login.jino.ru`. Эталонный POST входа из браузера ещё не захвачен: успешный HTTP-вход не доказывает полное совпадение с браузерным трафиком. Мутации восстановлены из frontend; живые изменения на аккаунте для их проверки не выполнялись. Совпадение Chrome TLS fingerprint не заявляется. См. [evidence.md](evidence.md).
