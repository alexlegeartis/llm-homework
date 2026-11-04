import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path('/content/llm-cache')
OUT = Path(os.environ.get('OUT_DIR', '/content/out'))
BASE = 'https://github.com/ggml-org/llama.cpp/releases/download/b11669/'
ASSETS = {
    'llama-b11669-bin-ubuntu-cuda-12.8-x64.tar.gz': '4703ed1a3cd6e8504affb6cb9866f501e96d634d68a002dc9a8251c9e2819b49',
    'cudart-llama-b11669-bin-ubuntu-cuda-12.8-x64.tar.gz': 'ab3eda89a82096bcba00b6448218c3c11eec2016b0f38d64884dc29736549f26',
}
VARIANTS = ['no_context', 'baseline', 'final', 'without_neighbors', 'without_expansion']


def run(*args, **kwargs):
    print('+', ' '.join(map(str, args)), flush=True)
    return subprocess.run(list(map(str, args)), check=True, cwd=ROOT, **kwargs)


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def bootstrap():
    CACHE.mkdir(parents=True, exist_ok=True)
    for key, name in [('UV_CACHE_DIR', 'uv'), ('UV_PYTHON_INSTALL_DIR', 'python'), ('PIP_CACHE_DIR', 'pip'), ('HF_HOME', 'huggingface')]:
        os.environ[key] = str(CACHE / name)
    if sys.version_info[:2] != (3, 11):
        run(sys.executable, '-m', 'pip', 'install', '--quiet', 'uv==0.12.1')
        uv = [sys.executable, '-m', 'uv']
        python = Path('/content/llm-venv/bin/python')
        if not python.exists():
            run(*uv, 'venv', '--python', '3.11.15', '--managed-python', python.parent.parent)
        run(*uv, 'pip', 'sync', '--python', python, ROOT / 'requirements.txt')
        os.execve(str(python), [str(python), '-u', *sys.argv], os.environ)
    cache_link = ROOT / '.cache'
    if not cache_link.exists():
        cache_link.symlink_to(CACHE, target_is_directory=True)


def download(url, path, expected):
    if path.exists():
        if digest(path) != expected:
            raise ValueError(f'SHA256 mismatch: {path}')
        return
    print('Downloading', path.name, flush=True)
    temporary = path.with_suffix(path.suffix + '.part')
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as response, temporary.open('wb') as handle:
        shutil.copyfileobj(response, handle, 8 * 1024 * 1024)
    if digest(temporary) != expected:
        raise ValueError(f'SHA256 mismatch: {temporary}')
    temporary.replace(path)
    print('Verified', path.name, path.stat().st_size, flush=True)


def prepare():
    run(sys.executable, 'prepare_data.py')
    run(sys.executable, 'prepare_models.py', '--config', 'config.json')
    run(sys.executable, 'build_index.py', '--corpus', 'homework_01_rag/data/corpus.jsonl', '--output', 'index', '--config', 'config.json')
    runtime = json.loads((ROOT / 'runtime.json').read_text())
    quant = runtime['quantization']
    model = CACHE / quant['file']
    download(f"https://huggingface.co/{quant['repository']}/resolve/{quant['revision']}/{quant['file']}?download=true", model, quant['sha256'])
    binary_dir = CACHE / 'llama-b11669-cuda12'
    for name, expected in ASSETS.items():
        archive = CACHE / name
        download(BASE + name, archive, expected)
        marker = binary_dir / (name + '.ready')
        if not marker.exists():
            binary_dir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive) as handle:
                handle.extractall(binary_dir, filter='data')
            marker.touch()
    server = next(binary_dir.rglob('llama-server'))
    libraries = sorted({str(path.parent) for path in binary_dir.rglob('*.so*')})
    os.environ['LD_LIBRARY_PATH'] = ':'.join(libraries + [os.environ.get('LD_LIBRARY_PATH', '')])
    os.environ.update(LLM_BASE_URL='http://127.0.0.1:8089/v1', LLM_MODEL=runtime['model'], LLM_API_KEY='local', SUBMISSION_ID='colab-' + time.strftime('%Y%m%d-%H%M%S', time.gmtime()))
    return runtime, model, server


def serve(runtime, model, binary, port=8089):
    settings = runtime['local_server']
    threads = min(settings['threads'], os.cpu_count() or 2)
    command = [str(binary), '-m', str(model), '--host', '127.0.0.1', '--port', str(port), '--ctx-size', str(settings['context_size'] * settings['parallel']), '--parallel', str(settings['parallel']), '--threads', str(threads), '--threads-batch', str(threads), '--batch-size', '256', '--ubatch-size', '128', '--jinja', '--alias', runtime['model'], '--cache-ram', '0', '--no-repack', '--n-gpu-layers', '99']
    with (OUT / ('server.log' if port == 8089 else f'server-{port}.log')).open('w') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline and process.poll() is None:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3) as response:
                if response.status == 200:
                    print(f'Qwen server ready on port {port}', flush=True)
                    return process
        except OSError:
            time.sleep(1)
    process.terminate()
    process.wait(timeout=30)
    raise RuntimeError('Server failed to start; inspect server.log')


def check_trace(folder, expected):
    traces = [json.loads(line) for line in (folder / 'trace.jsonl').read_text().splitlines()]
    if len(traces) != expected or any(t.get('error') or not t.get('usage_verified') for t in traces):
        raise RuntimeError(f'Incomplete or failed prediction: {folder}')


def predict(questions, folder):
    folder.mkdir(parents=True, exist_ok=True)
    run(sys.executable, 'predict.py', '--index', 'index', '--questions', questions, '--output', folder / 'answers.jsonl', '--trace', folder / 'trace.jsonl', '--config', 'config.json')
    check_trace(folder, len(Path(questions).read_text().splitlines()))


def benchmark(names, dataset, replicas=1):
    destination = OUT / ('benchmark' if dataset == 'dev' else 'own')
    questions = f'{dataset}_questions.jsonl'
    expected = len((ROOT / questions).read_text().splitlines())
    common = ['--index', 'index', '--questions', questions, '--gold', f'{dataset}_gold.jsonl', '--config', 'config.json']

    def variant(name):
        endpoint = f'http://127.0.0.1:{8089 + names.index(name) % replicas}/v1'
        env = dict(os.environ, LLM_BASE_URL=endpoint)
        folder = destination / '.parts' / name
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / 'run.log').open('w') as log:
            run(sys.executable, 'run_experiments.py', *common, '--output-dir', folder, '--names', name, stdout=log, stderr=subprocess.STDOUT, env=env)
        source = folder / 'experiments' / name
        check_trace(source, expected)
        shutil.copytree(source, destination / 'experiments' / name, dirs_exist_ok=True)

    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        list(pool.map(variant, names))
    run(sys.executable, 'run_experiments.py', *common, '--output-dir', destination, '--summarize-only')
    if dataset == 'own' and (destination / 'dev_answers.jsonl').exists():
        for kind in ('answers', 'trace'):
            (destination / f'dev_{kind}.jsonl').replace(destination / f'own_{kind}.jsonl')
    metadata = {name: json.loads((destination / '.parts' / name / 'run_metadata.json').read_text()) for name in names}
    (destination / 'run_metadata.json').write_text(json.dumps(metadata, indent=2))
    print((destination / 'experiments.csv').read_text(), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['smoke', 'benchmark', 'serve'], default='smoke')
    parser.add_argument('--names', nargs='+', choices=VARIANTS, default=VARIANTS)
    parser.add_argument('--dataset', choices=['dev', 'own'], default='dev')
    parser.add_argument('--replicas', type=int, choices=[1, 2], default=1)
    args = parser.parse_args()
    bootstrap()
    OUT.mkdir(parents=True, exist_ok=True)
    status_file = OUT / 'status.json'
    status = {'mode': args.mode, 'state': 'running', 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    status_file.write_text(json.dumps(status, indent=2))
    servers = []
    try:
        runtime, model, binary = prepare()
        metadata = {'runtime': runtime, 'gpu': subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader'], text=True).strip(), 'python': sys.version, 'build': json.loads((ROOT / 'index/build_metrics.json').read_text()), 'source_sha256': {str(path.relative_to(ROOT)): digest(path) for path in sorted(ROOT.rglob('*.py')) if '.cache' not in path.parts and 'index' not in path.parts}}
        for replica in range(args.replicas):
            servers.append(serve(runtime, model, binary, 8089 + replica))
        metadata['server_replicas'] = args.replicas
        metadata['profile_endpoints'] = {name: f'http://127.0.0.1:{8089 + i % args.replicas}/v1' for i, name in enumerate(args.names)}
        metadata['server_commands'] = [server.args for server in servers]
        metadata['gpu_memory_loaded'] = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,memory.free', '--format=csv,noheader'], text=True).strip()
        (OUT / 'colab_metadata.json').write_text(json.dumps(metadata, indent=2))
        if args.mode == 'smoke':
            sample = OUT / 'smoke_questions.jsonl'
            sample.write_text('\n'.join((ROOT / 'dev_questions.jsonl').read_text().splitlines()[:3]) + '\n')
            predict(sample, OUT / 'smoke')
        elif args.mode == 'benchmark':
            benchmark(args.names, args.dataset, args.replicas)
        else:
            while all(server.poll() is None for server in servers):
                time.sleep(1)
            raise RuntimeError('Qwen server stopped')
        status['state'] = 'succeeded'
    except BaseException as error:
        status.update(state='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        for server in servers:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
        status['finished_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        status_file.write_text(json.dumps(status, indent=2))


if __name__ == '__main__':
    main()