# Colab (T4)

## Запуск в ноутбуке Colab

Выберите среду с T4 и выполните ячейки:

```python
!git clone https://github.com/alexlegeartis/llm-homework.git /content/llm-homework
%cd /content/llm-homework/hw1
!python -m pip install --quiet uv==0.12.1
!python -m uv run --no-project --python 3.11.15 --with-requirements requirements.txt python -u colab/run_hw1.py --mode benchmark
```

Этот запуск использует Python 3.11 и зависимости из `requirements.txt`. Скрипт скачивает PDF, создаёт корпус и вопросы, готовит токенизатор и индекс, загружает закреплённые GGUF и Linux/CUDA-сборку llama.cpp и выполняет пять конфигураций. Результаты находятся в `/content/out/`, состояние — в `/content/out/status.json`. Все данные создаются кодом репозитория; CLI `build_index.py` и `predict.py` вызываются самим скриптом.

Для трёх пробных вопросов замените `--mode benchmark` на `--mode smoke`.

## Управление из Windows

Утилиты подключения адаптированы из `KissingNumber27/colab`. Нужен установленный `colab-cli` (проверено с 0.6.0). Авторизация Google общая для проектов; токены и файлы сессий не копируются в репозиторий.

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
