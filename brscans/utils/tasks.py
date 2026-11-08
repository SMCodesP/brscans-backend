import os
import threading
import time
from functools import wraps
from uuid import uuid4

import httpx
from django.conf import settings
from django.db import connections
from concurrent.futures import ThreadPoolExecutor


# Thread Pool Executor for local task queueing
_local_task_executor = None
_local_task_lock = threading.Lock()

# Fila local: ids das tasks queued/running (drain só conta)
_local_task_registry = set()

def get_executor():
    global _local_task_executor
    if _local_task_executor is None:
        with _local_task_lock:
            if _local_task_executor is None:
                max_workers = getattr(settings, "LOCAL_TASK_MAX_WORKERS", 3)
                _local_task_executor = ThreadPoolExecutor(
                    max_workers=max_workers,
                    thread_name_prefix="LocalTask"
                )
                print(f"[Local Task Queue] Thread pool initialized with max_workers={max_workers}")
    return _local_task_executor

def run_task_in_executor(task_id, func, *args, **kwargs):
    # This runs within a thread pool worker
    print(f"[Local Task] [RUNNING] Task '{func.__name__}' (ID: {task_id}) started executing...")

    try:
        func(*args, **kwargs)
        print(f"[Local Task] [SUCCESS] Task '{func.__name__}' (ID: {task_id}) completed successfully.")
    except Exception as e:
        print(f"[Local Task] [FAILED] Task '{func.__name__}' (ID: {task_id}) failed: {e}")
    finally:
        with _local_task_lock:
            _local_task_registry.discard(task_id)  # drain vê a fila esvaziar
        connections.close_all()

def dispatch_local_task(func, *args, **kwargs):
    task_id = str(uuid4())

    with _local_task_lock:
        _local_task_registry.add(task_id)

    print(f"[Local Task] [QUEUED] Task '{func.__name__}' (ID: {task_id}) queued.")

    executor = get_executor()
    executor.submit(run_task_in_executor, task_id, func, *args, **kwargs)
    return {"task_id": task_id, "status": "queued", "Message": f"Task {func.__name__} queued."}

def drain_local_tasks(timeout_seconds):
    """Espera a fila local esvaziar (a Lambda congela threads ao retornar)."""
    deadline = time.monotonic() + timeout_seconds
    pending = 0
    while time.monotonic() < deadline:
        with _local_task_lock:
            pending = len(_local_task_registry)
        if pending == 0:
            return {"drained": True, "pending": 0}
        time.sleep(0.5)
    return {"drained": False, "pending": pending}

def _in_lambda():
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

def _remote_dispatch(func, args, kwargs):
    """Invoke assíncrono (1 por task) na Lambda de trabalho.

    A thread pool local morria quando o handler retornava e a Lambda
    congelava. O teto de vazão é a concorrência reservada dessa Lambda.
    """
    from zappa.asynchronous import run

    # Sem nome explícito o zappa usa a função em que está rodando — a API,
    # com 512 MB e o teto do Gateway. O trabalho pesado tem que ir à worker.
    name = getattr(settings, "TASK_FUNCTION_NAME", "")
    if not name:
        raise RuntimeError(
            "TASK_FUNCTION_NAME ausente: @task invocaria a própria API. "
            "Configure a env na stage do Zappa."
        )

    return run(func, list(args), kwargs, remote_aws_lambda_function_name=name)


# 429 do Modal é recusa por concorrência: o pedido NÃO foi aceito, então
# repetir não duplica trabalho no ack (que ainda é idempotente por claim).
# 500 é o que o API Gateway devolve quando a brscans-fill bate na concorrência
# reservada (proteção das conexões do Mongo M0); 6 tentativas ≈ 31 s de espera.
_ACK_RETRY_STATUS = {429, 500, 502, 503, 504}
ACK_ATTEMPTS = 6


class Saturation(RuntimeError):
    """Ack recusou por carga (429/5xx) mesmo após as tentativas.

    A página não está quebrada: não cabia agora. Quem chama deve reagendar
    (backoff longo) sem gastar tentativa.
    """


def _post_ack(url, payload):
    """POST de disparo com ack rápido: 2xx é sucesso; retenta 429/5xx e conexão.

    `url` pode listar várias contas separadas por vírgula: o id da imagem divide
    as páginas entre elas e, se uma recusar, a página vai na hora para a outra
    (o claim no Mongo compartilhado impede trabalho duplicado). Com uma só conta,
    ReadTimeout não retenta: o pedido pode ter sido aceito, e o claim + o reparo
    resolvem a página no próximo ciclo."""
    urls = url.split(",")
    first = int(payload.get("image_id") or payload.get("id") or 0)
    for attempt in range(ACK_ATTEMPTS):
        last = attempt == ACK_ATTEMPTS - 1
        target = urls[(first + attempt) % len(urls)]
        try:
            response = httpx.post(target, json=payload, timeout=10.0)
        except httpx.ReadTimeout:
            if last or len(urls) == 1:
                raise
        except httpx.TransportError:
            if last:
                raise
        else:
            if response.status_code < 400:
                return response.json() if response.content else {}
            # Conta travada pode responder qualquer erro; 400/422 é o pedido.
            retry = response.status_code in _ACK_RETRY_STATUS or (
                len(urls) > 1 and response.status_code not in (400, 422)
            )
            if not retry:
                raise RuntimeError(f"{target} respondeu {response.status_code}")
            if last:
                raise Saturation(f"{target} respondeu {response.status_code}")
        if (attempt + 1) % len(urls) == 0:
            time.sleep(2**attempt)


def task(func):
    """Torna a função assíncrona e confiável.

    Dentro da Lambda o disparo é um invoke na Lambda de trabalho
    (`TASK_FUNCTION_NAME`); fora (dev/testes) segue a thread pool.
    O wrapper expõe `.sync` com o corpo original, que os chamadores usam
    para rodar na hora e ver o erro (sem virar outro disparo).
    """
    @wraps(func)
    def wrapper(*w_args, **w_kwargs):
        if _in_lambda() and not getattr(settings, "LOCAL_TASK_FORCE", False):
            return _remote_dispatch(func, w_args, w_kwargs)
        return dispatch_local_task(func, *w_args, **w_kwargs)

    wrapper.sync = func
    return wrapper
