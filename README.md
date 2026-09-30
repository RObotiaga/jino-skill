# Jino skill + CLI

Skill для управления доменами Jino через Python CLI и прямые HTTP-запросы. Поддерживает автоматический вход по login/password, чтение доменов и DNS, изменение IP, управление записями, настройками, NS, контактами и SSL.

## Установка skill (Windows)

В PowerShell:

```powershell
git clone https://github.com/RObotiaga/jino-skill.git "$env:USERPROFILE\.codex\skills\jino-control"
& "$env:USERPROFILE\.codex\skills\jino-control\scripts\install.ps1"
```

Скрипт создаёт отдельное Python-окружение и устанавливает SDK. Нужны Python 3.10+ с командой `py` и Git. После обновления списка skills доступен `$jino-control`.

## Учётные данные

Один раз запустите сами в интерактивном терминале:

```powershell
$jino = "$env:USERPROFILE\.codex\skills\jino-control\scripts\jino.ps1"
& $jino auth configure
& $jino auth check
```

Пароль вводится скрыто. Профиль шифруется Windows DPAPI для текущего пользователя и хранится вне репозитория, в `%LOCALAPPDATA%/JinoCLI/credentials.dpapi`. Альтернатива — переменные среды `JINO_LOGIN` и `JINO_PASSWORD`. Пароли не передаются в аргументах CLI. `auth clear` удаляет сохранённый профиль.

## Управление

```powershell
& $jino domains list
& $jino dns list example.com --type A
& $jino dns ip example.com --record-id 123 --ip 203.0.113.42
& $jino dns ip example.com --record-id 123 --ip 203.0.113.42 --expected-value 203.0.113.10 --apply
```

Без `--apply` команда изменения показывает план. С `--apply` выполняется мутация. IP меняется с сохранением имени и типа записи. `--expected-value` проверяет значение перед записью, но не обеспечивает атомарность на сервере.

Компактный JSON, фильтры и ограничение списков уменьшают объём контекста агента. Подтверждённое изменение возвращает `outcome=applied` и `verification=read_back`. При `RESULT_UNVERIFIED`, `WRITE_RESULT_UNKNOWN` или `PARTIAL_UPDATE` прочитайте текущее состояние перед повтором. Selenium, Playwright, Puppeteer и другие эмуляторы браузера не используются.

## CLI и SDK отдельно

```powershell
py -m pip install .
jino --help
```

CLI также запускается как `python -m jino_domains_sdk`. Async SDK экспортирует `JinoClient`.

## Проверки и ограничения

HTTP-вход и чтение доменов, DNS, настроек, NS и SSL проверены на реальном аккаунте. Исправлена цепочка перенаправлений через `login.jino.ru`. В репозитории есть пять регрессионных тестов обработки входа:

```powershell
& "$env:USERPROFILE\.codex\skills\jino-control\runtime\Scripts\python.exe" -B -m unittest discover -s "$env:USERPROFILE\.codex\skills\jino-control\tests" -v
```

Живые мутации не проверялись. Для сложных DNS, контактов, SSL и сброса зоны автоматическая проверка результата пока не реализована: завершённый запрос возвращает `RESULT_UNVERIFIED`. Полное совпадение запросов входа и мутаций с браузером и TLS fingerprint Chrome не заявляется. Регистрация, покупка, перенос, удаление домена и платное продление не поддерживаются.

## Документация

- [Skill для агента](SKILL.md)
- [Справка CLI](docs/CLI.md)
- [Python SDK](docs/SDK.md)
- [Источники и результаты проверки](docs/evidence.md)
