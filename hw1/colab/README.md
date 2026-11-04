# Colab (T4)

Утилиты подключения перенесены из `D:/GitHubD/KissingNumber27/colab` и адаптированы для этого задания. Нужен установленный `colab-cli` (проверено с 0.6.0). Авторизация Google общая для проектов; токены и файлы сессий не копируются в репозиторий.

Команды выполняются из `hw1/` (из корня репозитория сначала `cd hw1`):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
. ./project_env.ps1
./colab/colab.ps1 sessions
./colab/run.ps1 -Project ./colab/project.json -Sync -Job ./colab/jobs/smoke.json
./colab/run.ps1 -Project ./colab/project.json -Poll
./colab/run.ps1 -Project ./colab/project.json -Fetch ./.cache/colab-results
```

Если авторизации ещё нет, выполните `./colab/colab_account.ps1 -New homework`. Для нескольких аккаунтов есть `colab_account.ps1`; перед переключением учитывайте запущенные сессии других проектов.

Полная оценка пяти конфигураций на открытом наборе:

```powershell
./colab/run.ps1 -Project ./colab/project.json -Sync -Job ./colab/jobs/benchmark.json
```

Дождитесь `state: succeeded` в скачанном `status.json`. `JOB_ALIVE False` само по себе не означает успех. Ответы, расход токенов, таблица и сведения об оборудовании находятся в скачанном каталоге. Ошибка API делает прогон неуспешным.

Python 3.11, точные зависимости, учебник, токенизатор, GGUF и CUDA-сборка llama.cpp подготавливаются на VM. Файлы проверяются по SHA-256. Веса и окружение сохраняются в `/content/llm-cache` и `/content/llm-venv`, поэтому повторная синхронизация кода не скачивает их заново. Поиск остаётся на CPU; только Qwen использует GPU. В пакет кода не входят локальные данные, индекс, веса, окружение и кэши. Локальные временные файлы находятся на D через `project_env.ps1`.

Задание запускается отдельно от интерактивного ядра. Это позволяет опрашивать VM и забирать результаты во время работы. Выполняйте команды CLI последовательно: его файлы авторизации и сессий общие с другими проектами.

```powershell
./colab/run.ps1 -Project ./colab/project.json -Check
./colab/run.ps1 -Project ./colab/project.json -StopJob
./colab/run.ps1 -Project ./colab/project.json -Stop
```

`-StopJob` останавливает текущую задачу, `-Stop` освобождает всю сессию `llm-homework`. Сначала скачайте результаты: Colab не гарантирует сохранение VM. Если после ошибки 404/401 сессия отображается как `[?]`, восстановите привязку командой `./colab/reattach.ps1`, затем повторите команду. Это обновляет доступ к существующей VM без её пересоздания.
Для отдельной проверки итоговой системы используйте `jobs/final.json`; `jobs/serve.json` оставляет endpoint работающим внутри VM до `-StopJob`. Перед повторным `-Sync` дождитесь завершения задачи или остановите её.
