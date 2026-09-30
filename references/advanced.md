# Дополнительные операции

`$jino` задаётся в основном skill. Примеры `--apply` используют разрешение, уже данное пользователем для конкретного действия.

## Настройки

```powershell
& $jino settings get example.com
& $jino domain nameservers example.com
& $jino domain renewal example.com
& $jino settings set example.com --ipv6 on
& $jino settings set example.com --nameserver ns1.example.net --nameserver ns2.example.net --apply
& $jino https set example.com --enabled on --apply
```

`--www-mode` принимает строку режима Jino: сначала прочитай настройки и уточни допустимый режим; не придумывай enum. При нескольких параметрах возможен частичный результат. Команда renewal только читает информацию.

## Сложные DNS

```powershell
& $jino dns add example.com --type CNAME --name www --cname example.com --apply
& $jino dns add example.com --type MX --name @ --mx mail.example.com --priority 10 --apply
& $jino dns add example.com --type TXT --name _acme-challenge --txt 'verification-value' --apply
& $jino dns update example.com --record-id 123 --type MX --mx mail.example.com --priority 20 --apply
```

`dns update` сохраняет имя, если `--name` не задан. Для MX, SRV, CAA передай все поля типа при изменении: read-query не даёт структурированные старые поля, и CLI не угадывает их. SSHFP и NAPTR доступны для добавления; текущий frontend не предоставляет их редактирование. Для SRV имя задаётся полем `--service`; `--name` не принимается. См. `dns add --help` для полного набора полей. NAPTR `--flags` — строка, CAA `--flags` — число. TXT/SPF/CAA проходят browser btoa: текст должен помещаться в Latin-1.

A/AAAA и удаление проверяются повторным чтением зоны. Для других типов формат display-value пока недостаточен для полной проверки: после запроса CLI возвращает `RESULT_UNVERIFIED`, код 6; прочитай `dns list` и сопоставь состояние, не повторяй команду автоматически. Создание или изменение записи не означает завершение распространения DNS.

## Домены и поддомены

```powershell
& $jino domains add example.com --apply
& $jino subdomain add example.com --name api --apply
```

`domains add` добавляет уже существующий домен в аккаунт; Jino может запросить подтверждение владения. `--send-email` явно запрашивает письмо подтверждения.

## Контакты и SSL

```powershell
& $jino contacts get example.com
& $jino contacts get example.com --full
& $jino contacts update example.com --type CONTACT_TYPE --file C:\secure\contacts.json --apply
& $jino ssl get example.com
& $jino ssl request example.com --apply
& $jino ssl upload example.com --cert-file C:\secure\cert.pem --key-file C:\secure\key.pem --apply
& $jino ssl delete example.com --apply
```

Тип контакта и JSON-поля берутся из текущего ответа Jino, а не выдумываются. Полные контакты содержат персональные данные: читай их только для нужного изменения. Контактный JSON и PEM хранятся в локальных файлах; содержимое ключа не выводится. Для пароля ключа передай имя заранее настроенной переменной через `--password-env`, значение не включай в команду. `ssl request --wildcard` запрашивает wildcard.

Для контактов и SSL автоматическое подтверждение результата ещё не реализовано: завершённый HTTP-запрос возвращает `RESULT_UNVERIFIED`; затем прочитай `contacts get` / `ssl get`. Выпуск сертификата асинхронный: успешная отправка не доказывает, что сертификат уже выпущен.

## Сброс зоны и ошибки

```powershell
& $jino dns reset example.com
& $jino dns reset example.com --confirm-domain example.com --apply
```

Сброс заменяет всю зону. Выполняй только при явном запросе пользователя на полный сброс. Прочитай записи перед сбросом и сохрани их, если пользователь запросил резервную копию. CLI не обещает автоматическое восстановление зоны.

Коды выхода: 0 — чтение, план или подтверждённое изменение; 2 — аргументы/файл; 3 — вход; 4 — недоступный объект или защита записи; 5 — запрос/протокол; 6 — неподтверждённая запись или частичный результат; 130 — прерывание. JSON содержит `ok` и `data` либо `error.code`; ориентируйся на поля, не на текст сообщения.
