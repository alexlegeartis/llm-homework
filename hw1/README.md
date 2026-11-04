# ДЗ 1. Доказательный RAG по ТФКП

**Автор:** Кравацкий Алексей Юрьевич, **группа М05-602а**.

Дедлайн: **4 ноября 2026 включительно**. [Условие](homework_01_rag/materials/homework_01_rag.md), [15 исходных QA](homework_01_rag/materials/tfkp_15_qa.md), [отчёт](report.md).

## Что где лежит

[Запуск](#воспроизведение-из-исходников) · [Эксперименты](#оценка-и-эксперименты) · [Технические тесты](tests/) · [Colab](colab/)

Все пути в этом разделе указаны относительно `hw1/`. В корне репозитория находится только README курса и папка этого задания.

### Папки

| Путь | Что внутри и когда нужно |
| --- | --- |
| [`homework_01_rag/`](homework_01_rag/) | Реализация: извлечение PDF, BM25, подготовка контекста, вызов Qwen и оценка. Внутри есть карта модулей. |
| [`homework_01_rag/materials/`](homework_01_rag/materials/) | Исходное условие и 15 QA-пар преподавателя. Из них код получает ссылку на PDF и создаёт dev-набор. |
| [`experiments/`](experiments/) | Результаты пяти способов ответа на 15 вопросах из условия и дополнительной проверки на восьми своих вопросах. Подпапки описаны внутри. |
| [`tests/`](tests/) | Необязательные технические проверки кода; состав и команда запуска описаны внутри. |
| [`colab/`](colab/) | Дополнительные инструменты запуска того же решения на T4 и получения результатов. Внутри — инструкция и карта служебных файлов. |

### Файлы непосредственно в `hw1/`

| Файлы | Назначение |
| --- | --- |
| [`prepare_data.py`](prepare_data.py), [`prepare_models.py`](prepare_models.py), [`build_index.py`](build_index.py) | Создают корпус, наборы вопросов с эталонами, токенизатор и индекс; команды приведены ниже. |
| [`predict.py`](predict.py), [`evaluate.py`](evaluate.py), [`run_experiments.py`](run_experiments.py) | Предсказание, оценка и воспроизведение пяти экспериментов. Одноимённые модули в `homework_01_rag/` содержат реализацию; эти файлы — короткие CLI-точки входа. |
| [`config.json`](config.json), [`runtime.json`](runtime.json), [`requirements.txt`](requirements.txt) | Настройки поиска, модель и параметры генерации, закреплённые зависимости. |
| [`dev_questions.jsonl`](dev_questions.jsonl), [`dev_gold.jsonl`](dev_gold.jsonl) | 15 вопросов из исходных QA и эталоны для оценки. Предсказание получает только вопросы. |
| [`own_questions.jsonl`](own_questions.jsonl), [`own_gold.jsonl`](own_gold.jsonl) | 8 подготовленных мною вопросов и правильные ответы с подтверждающими фрагментами. |
| [`dev_answers.jsonl`](dev_answers.jsonl), [`dev_trace.jsonl`](dev_trace.jsonl) | Сохранённый dev-прогон: ответы и отладочные сведения о вызовах, токенах, времени и найденных фрагментах. Версия кода и метрики сохранены в `run_metadata.json`, описание прогонов в `experiments/`. |
| [`experiments.csv`](experiments.csv), [`report.md`](report.md) | Сводные результаты и отчёт с методом, абляциями, ошибками и измерениями. |
| [`corpus_manifest.json`](corpus_manifest.json), [`run_metadata.json`](run_metadata.json) | Дополнительные сведения для проверки воспроизводимости: хеши исходников данных, параметры и окружение прогона. |
| [`.env.example`](.env.example) | Пример значений API. Файл автоматически не загружается: переменные задаются в терминале, как показано ниже. |
| [`project_env.ps1`](project_env.ps1), [`serve_model.ps1`](serve_model.ps1) | Дополнительные инструменты Windows: временные файлы и кэши в папке проекта, запуск локального Qwen. |
| [`.gitignore`](.gitignore), [`.gitattributes`](.gitattributes) | Исключения из Git и настройки окончаний строк. |

`colab/` и PowerShell-скрипты нужны при выборе соответствующего способа запуска. Подробные результаты и метаданные дополняют обязательные `experiments.csv`, итоговые dev-файлы и отчёт.

### Что создаётся локально и не хранится в Git

| Путь по умолчанию | Содержимое и источник |
| --- | --- |
| `homework_01_rag/data/` | `textbook.pdf` и `corpus.jsonl`; создаёт `prepare_data.py`. |
| `index/` | Поисковый индекс, копия токенизатора и `build_metrics.json`; создаёт `build_index.py --output index`. |
| `.venv/` | Локальное окружение Python. |
| `.cache/` | Скачанные модели и токенизатор, временные файлы и кэши. `prepare_models.py` использует `.cache/qwen-tokenizer/`, локальный сервер — `.cache/runtime/`, `project_env.ps1` — `.cache/work/`. |

## Воспроизведение из исходников

Нужен Python **3.11**. Команды для Linux, начиная с корня репозитория:

```bash
cd hw1
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python prepare_data.py
python prepare_models.py --config config.json
python build_index.py --corpus homework_01_rag/data/corpus.jsonl --output index --config config.json
```

Все последующие команды выполняются из `hw1/`.

`prepare_data.py` скачивает PDF по публичной ссылке из условия, проверяет SHA-256 и пересоздаёт корпус и наборы вопросов с эталонами. Для уже скачанного учебника используйте `python prepare_data.py --pdf /path/to/textbook.pdf`.

## Подключение Qwen

`predict.py` обращается к OpenAI-совместимому Chat Completions API с **Qwen3.5-4B**. Для запуска с доступным API задайте переменные окружения в том же терминале, из которого будете вызывать `predict.py`:

| Переменная | Значение |
| --- | --- |
| `LLM_BASE_URL` | Базовый адрес API, например `http://127.0.0.1:8089/v1`. Клиент добавляет к нему `/chat/completions`. |
| `LLM_MODEL` | Имя модели на сервере: в наших скриптах это `Qwen/Qwen3.5-4B`. |
| `LLM_API_KEY` | Ключ доступа к серверу. Для локального llama.cpp из наших скриптов используется `local`. |
| `SUBMISSION_ID` | Идентификатор работы для заголовка `X-Submission-ID`, например `kravatskiy-hw1`. |

Пример команд в разделе [«Предсказание»](#предсказание) рассчитан на Qwen, уже запущенный на той же машине на порту 8089. Для другого сервера подставьте его базовый URL, имя модели и ключ. Проверяющий предоставляет свой endpoint. Он должен поддерживать параметры генерации из [runtime.json](runtime.json), включая thinking и `thinking_budget_tokens`; локальный llama.cpp из наших скриптов их поддерживает.

В режиме [Colab](#запуск-на-colab) скрипт сам запускает Qwen и задаёт эти переменные для процессов внутри VM.

## Предсказание

В терминале с активным окружением:

```bash
export LLM_BASE_URL="http://127.0.0.1:8089/v1"
export LLM_MODEL="Qwen/Qwen3.5-4B"
export LLM_API_KEY="local"
export SUBMISSION_ID="kravatskiy-hw1"
python predict.py --index index --questions dev_questions.jsonl --output answers.jsonl --trace trace.jsonl --config config.json
```

В `--output` записываются ответы, в `--trace` отладочные данные. Пути CLI могут быть абсолютными; запуск возможен из другой папки. [Формат ответов](homework_01_rag/materials/homework_01_rag.md#3-форматы) задан условием.

## Архитектура

PDF → BM25 → контекст → один вызов Qwen3.5-4B. Поиск выполняется на CPU, LLM доступна через отдельный API. Подробности извлечения формул, поиска, контекста и отказов — в [отчёте](report.md#данные-и-метод).

## Оценка и эксперименты

```bash
python evaluate.py --questions dev_questions.jsonl --gold dev_gold.jsonl --answers dev_answers.jsonl --trace dev_trace.jsonl --corpus homework_01_rag/data/corpus.jsonl
python run_experiments.py --index index --questions dev_questions.jsonl --gold dev_gold.jsonl --config config.json --output-dir .
```

Состав сохранённых прогонов, версии кода и назначение файлов описаны в [`experiments/`](experiments/); результаты и выводы абляций — в [отчёте](report.md#эксперименты). Для выбора прогонов используйте `--names final without_expansion`, для пересчёта метрик без вызовов модели — `--summarize-only`.

## Ресурсы

Для локального сервера Qwen предусмотрено 8 ГиБ RAM и около 10 ГБ диска. При подключении к готовому API веса модели на машине клиента не нужны. Измеренные время сборки, RAM, размер индекса и оборудование приведены в [отчёте](report.md#ресурсы-и-воспроизводимость); [внешние инструменты и помощь ИИ](report.md#внешние-инструменты-и-помощь-ии) описаны там же.

## Запуск на Colab

[Инструкция Colab](colab/) содержит команды для ноутбука и управления с Windows, назначение служебных файлов и пути к результатам на VM.

## Локальные инструменты Windows

Подготовка окружения в PowerShell из `hw1/`:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
. ./project_env.ps1
py -3.11 -m venv .venv
. ./.venv/Scripts/Activate.ps1
python -m pip install -r requirements.txt
```

Если `py` не видит Python 3.11, окружение можно создать командой `uv venv --python 3.11 --seed .venv`. Остальные Python-команды совпадают с приведёнными выше; переменные окружения задаются как `$env:LLM_BASE_URL = "..."`.

`project_env.ps1` создаёт временные файлы и кэши в `.cache/work/` относительно папки самого скрипта (`hw1/`). Путь определяется через `$PSScriptRoot`, без привязки к букве диска или имени пользователя. Переменные окружения меняются только для текущего процесса и его потомков; при обычном запуске Python CLI этот вспомогательный скрипт не требуется.

Для запуска локального Qwen есть `powershell -ExecutionPolicy Bypass -File serve_model.ps1`: он скачивает закреплённые Qwen3.5-4B Q8_0 и llama.cpp, проверяет SHA-256 и открывает API на `127.0.0.1:8089`.
