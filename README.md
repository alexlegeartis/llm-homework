# llm-homework

Домашние задания по курсу «Большие языковые модели», 9-й семестр, 2026.

**Автор:** Кравацкий Алексей Юрьевич, **группа М05-602а**.

## ДЗ 1: доказательный RAG по ТФКП

Дедлайн: **4 ноября 2026 включительно**. [Условие](homework_01_rag/materials/homework_01_rag.md), [исходные 15 QA](homework_01_rag/materials/tfkp_15_qa.md), [отчёт](report.md).

Реализация находится в `homework_01_rag/`. Скрипты запуска, настройки и результаты вынесены в корень по требованиям сдачи. Индекс, корпус и веса создаются локально и исключены из Git.

### Подготовка

Python **3.11**, команды из корня репозитория:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python prepare_data.py
python prepare_models.py --config config.json --output .cache/e5
python build_index.py --corpus homework_01_rag/data/corpus.jsonl --output index --config config.json
```

Если `py` не видит Python 3.11, окружение можно создать через `uv venv --python 3.11 --seed .venv`. На рабочем компьютере окружение `.venv` уже подготовлено; достаточно активировать его.

`prepare_data.py` скачивает проверяемый по SHA-256 учебник, восстанавливает текст и формулы всех 147 страниц, создаёт корпус, dev-набор и восемь авторских вопросов. Для уже скачанного PDF: `python prepare_data.py --pdf /path/to/textbook.pdf`. Повторная подготовка воспроизводит ID фрагментов. Файлы из ошибочного списка «В комплекте» подготовлены самостоятельно согласно уточнению преподавателя.

Сеть нужна на этапе подготовки. При сборке индекса и предсказании модели уже находятся на диске; предсказание обращается только к заданному LLM endpoint. На Linux активация окружения: `source .venv/bin/activate`.

### Локальная Qwen

На Windows в отдельном терминале:

```powershell
powershell -ExecutionPolicy Bypass -File serve_model.ps1
```

Скрипт скачает закреплённые llama.cpp и Qwen3.5-4B Q4_K_M, проверит SHA-256 и запустит Chat Completions API на `127.0.0.1:8089`. Первое скачивание — около 2,8 ГБ. На Linux можно собрать [llama.cpp b11669](https://github.com/ggml-org/llama.cpp/releases/tag/b11669) и запустить `llama-server` с теми же аргументами из скрипта. Ревизии, квантизация, параметры генерации и лимиты записаны в [runtime.json](runtime.json).

### Предсказание

Во втором терминале с активным Python-окружением:

```powershell
$env:LLM_BASE_URL = "http://127.0.0.1:8089/v1"
$env:LLM_MODEL = "Qwen/Qwen3.5-4B"
$env:LLM_API_KEY = "local"
$env:SUBMISSION_ID = "kravatskiy-hw1"
python predict.py --index index --questions dev_questions.jsonl --output answers.jsonl --trace trace.jsonl --config config.json
```

Проверяющий может заменить переменные endpoint. В каждый запрос передаются `X-Question-ID` и `X-Submission-ID`. Для LLM варианты обозначаются A–F по текущему порядку; выбранные метки переводятся в исходные ID. Скрипт не читает эталоны и не переносит диалог между вопросами. Пути CLI могут быть абсолютными, запуск возможен из другой папки.

В выходе — один JSON на вопрос: выбранные ID, отказ, обоснование и до четырёх исходных `block_id`. В trace сохраняются реальные `usage` API, отдельные вызовы и отправленные фрагменты. Техническая ошибка отмечается в trace и получает ноль при оценке.

### Архитектура

1. Из PDF извлекаются символы и координаты: дроби, индексы и надчёркивания переводятся в текст. Фрагменты ограничены страницей и абзацами; целевой размер около 850, максимум 1500 символов.
2. В индексе: BM25 и CPU-векторы [multilingual-e5-small](https://huggingface.co/intfloat/multilingual-e5-small), 118 млн параметров, закреплённая ревизия, ONNX int8. Усреднение по маске и нормализация; префиксы `query:` / `passage:`.
3. Qwen формулирует короткий поисковый запрос. BM25 и dense дают по 18 кандидатов; Reciprocal Rank Fusion с константой 60 выбирает шесть.
4. Целые фрагменты помещаются в бюджет контекста. Второй вызов Qwen возвращает JSON по схеме; код проверяет ID, ссылки и правила отказа.

Это фиксированная цепочка из двух вызовов. Повторных попыток нет. При `max_tokens=512` консервативная оценка по UTF-8 ограничивает вход каждого запроса; фактический расход проверяется по API. Thinking отключён, температура 0. Отказ должен обозначать недостаточность оснований; ошибочный отказ из-за пропуска поиска также считается ошибкой.

### Оценка и эксперименты

```powershell
python evaluate.py --questions dev_questions.jsonl --gold dev_gold.jsonl --answers dev_answers.jsonl --trace dev_trace.jsonl --corpus homework_01_rag/data/corpus.jsonl
python run_experiments.py --index index --questions dev_questions.jsonl --gold dev_gold.jsonl --config config.json --output-dir .
python -m unittest discover -s tests -v
```

Пять конфигураций: без контекста; BM25 с одним поиском и вызовом; итоговая система; без dense; без rewriting. Параметры генерации одинаковы. Результаты — [experiments.csv](experiments.csv), ответы и trace каждого прогона — `experiments/`. Можно выбрать прогоны через `--names final without_dense`; `--summarize-only` пересчитывает метрики из готовых файлов без LLM.

На открытом наборе лучший профиль — [без rewriting](experiments/without_rewrite/config.json): 11/15 точных ответов, Q=0,701. Для него передайте этот файл в `--config`. Корневой `config.json` и `dev_*.jsonl` сохраняют проверенную полную цепочку; её неудачное улучшение и обе абляции разобраны в отчёте.

Поскольку официальный baseline и его `C_ref` не были выданы, локальная эффективность считается относительно измеренного BM25-baseline. Это локальное сравнение, не официальный балл. Ручную содержательную проверку обоснований автоматическая метрика не заменяет.

### Ресурсы и воспроизводимость

Поиск и embeddings выполняются на CPU; LLM запущена отдельным процессом. Для локального запуска предусмотрено 8 ГиБ RAM и около 4 ГБ свободного диска. Измерения сборки и оборудования находятся в отчёте, `index/build_metrics.json` и `run_metadata.json`. Все зависимости, включая транзитивные, закреплены в `requirements.txt`; ревизии моделей — в `config.json` и `runtime.json`.

Подготовка не вызывает LLM. Корпус не дополнен генеративным текстом, обучение отсутствует. Использованы PyMuPDF, ONNX Runtime, Hugging Face Tokenizers, Snowball и llama.cpp. При разработке, проверке кода и подготовке отчёта использовался Codex; все экспериментальные ответы сгенерированы только заданной [Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B), квантизация — [Unsloth](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF).
