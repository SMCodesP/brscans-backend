import os
import threading
from functools import wraps
from datetime import datetime
from uuid import uuid4
from django.conf import settings
from django.db import connections
from concurrent.futures import ThreadPoolExecutor

# Thread Pool Executor for local task queueing
_local_task_executor = None
_local_task_lock = threading.Lock()

# Task registry and capped history
_local_task_registry = {}  # task_uuid -> task_info
_completed_tasks_history = []
_failed_tasks_history = []

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
    with _local_task_lock:
        if task_id in _local_task_registry:
            _local_task_registry[task_id]["status"] = "running"
            _local_task_registry[task_id]["started_at"] = datetime.now().isoformat()
            
    print(f"[Local Task] [RUNNING] Task '{func.__name__}' (ID: {task_id}) started executing...")
    
    try:
        func(*args, **kwargs)
        with _local_task_lock:
            if task_id in _local_task_registry:
                _local_task_registry[task_id]["status"] = "completed"
                _local_task_registry[task_id]["ended_at"] = datetime.now().isoformat()
                # Move to completed history
                task_info = _local_task_registry.pop(task_id)
                _completed_tasks_history.append(task_info)
                # Cap history at 50 to prevent memory growth
                if len(_completed_tasks_history) > 50:
                    _completed_tasks_history.pop(0)
        print(f"[Local Task] [SUCCESS] Task '{func.__name__}' (ID: {task_id}) completed successfully.")
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        with _local_task_lock:
            if task_id in _local_task_registry:
                _local_task_registry[task_id]["status"] = "failed"
                _local_task_registry[task_id]["ended_at"] = datetime.now().isoformat()
                _local_task_registry[task_id]["error"] = str(e)
                _local_task_registry[task_id]["traceback"] = tb
                # Move to failed history
                task_info = _local_task_registry.pop(task_id)
                _failed_tasks_history.append(task_info)
                if len(_failed_tasks_history) > 50:
                    _failed_tasks_history.pop(0)
        print(f"[Local Task] [FAILED] Task '{func.__name__}' (ID: {task_id}) failed: {e}")
    finally:
        connections.close_all()

def dispatch_local_task(func, *args, **kwargs):
    task_id = str(uuid4())
    task_info = {
        "id": task_id,
        "name": func.__name__,
        "args": [str(a) for a in args],
        "kwargs": {k: str(v) for k, v in kwargs.items()},
        "status": "queued",
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "ended_at": None,
        "error": None,
        "traceback": None,
    }
    
    with _local_task_lock:
        _local_task_registry[task_id] = task_info
        
    print(f"[Local Task] [QUEUED] Task '{func.__name__}' (ID: {task_id}) queued.")
    
    executor = get_executor()
    executor.submit(run_task_in_executor, task_id, func, *args, **kwargs)
    return {"task_id": task_id, "status": "queued", "Message": f"Task {func.__name__} queued."}

def get_local_tasks_status():
    with _local_task_lock:
        running = []
        queued = []
        for task_id, task_info in _local_task_registry.items():
            if task_info["status"] == "running":
                running.append(task_info)
            else:
                queued.append(task_info)
                
        return {
            "queued_count": len(queued),
            "running_count": len(running),
            "completed_count": len(_completed_tasks_history),
            "failed_count": len(_failed_tasks_history),
            "running": running,
            "queued": queued,
            "completed": list(reversed(_completed_tasks_history))[:20],
            "failed": list(reversed(_failed_tasks_history))[:20],
        }

def task(*args, **kwargs):
    """
    Custom task decorator wrapper.
    If settings.USE_ZAPPA_TASKS is True, it delegates to zappa.asynchronous.task.
    Otherwise (localhost / development), it queues execution in a ThreadPoolExecutor.
    """
    if len(args) == 1 and callable(args[0]):
        func = args[0]
        
        if getattr(settings, "USE_ZAPPA_TASKS", False):
            from zappa.asynchronous import task as zappa_task
            return zappa_task(func)
            
        @wraps(func)
        def wrapper(*w_args, **w_kwargs):
            return dispatch_local_task(func, *w_args, **w_kwargs)
        return wrapper
        
    else:
        decorator_args = args
        decorator_kwargs = kwargs
        
        def decorator(func):
            if getattr(settings, "USE_ZAPPA_TASKS", False):
                from zappa.asynchronous import task as zappa_task
                return zappa_task(*decorator_args, **decorator_kwargs)(func)
                
            @wraps(func)
            def wrapper(*w_args, **w_kwargs):
                return dispatch_local_task(func, *w_args, **w_kwargs)
            return wrapper
            
        return decorator
