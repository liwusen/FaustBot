# ...existing code...
from typing import List, Union, Literal, Optional
import datetime
import time
import queue
import json
from pathlib import Path
import threading
import os
import random
try:
    import faust_backend.config_loader as conf
except ImportError:
    import config_loader as conf
from pydantic import BaseModel, Field, field_validator

TRIGGERS_FILE = Path(conf.DATA_ROOT) / "triggers.json"
exitflag=False
trigger_queue: "queue.Queue[dict]" = queue.Queue()


class BaseTrigger(BaseModel):
    id: str
    type: str
    recall_description: Optional[str] = None

    model_config = {"extra": "forbid"}


class DateTimeTrigger(BaseTrigger):
    type: Literal["datetime"]
    target: datetime.datetime

    @field_validator("target", mode="before")
    def parse_target(cls, v):
        if isinstance(v, str):
            # accept 'YYYY-MM-DD HH:MM:SS' or ISO format
            try:
                return datetime.datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
            except Exception:
                return datetime.datetime.fromisoformat(v)
        return v


class IntervalTrigger(BaseTrigger):
    type: Literal["interval"]
    interval_seconds: int = Field(..., ge=1)
    last_triggered: float = Field(default_factory=time.time)


class PyEvalTrigger(BaseTrigger):
    type: Literal["py-eval"]
    eval_code: str


Trigger = Union[DateTimeTrigger, IntervalTrigger, PyEvalTrigger]


class TriggerStore(BaseModel):
    watchdog: List[Trigger] = Field(default_factory=list)

    def save(self):
        # use model_dump 并确保 datetime 可序列化
        data = {"watchdog": [t.model_dump() for t in self.watchdog]}
        TRIGGERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with TRIGGERS_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4, default=str)

    @classmethod
    def load(cls) -> "TriggerStore":
        if not TRIGGERS_FILE.exists():
            store = cls()
            store.save()
            return store
        try:
            raw = json.load(TRIGGERS_FILE.open("r", encoding="utf-8"))
            items = []
            for t in raw.get("watchdog", []):
                ttype = t.get("type")
                if ttype == "datetime":
                    items.append(DateTimeTrigger.model_validate(t))
                elif ttype == "interval":
                    items.append(IntervalTrigger.model_validate(t))
                elif ttype == "py-eval":
                    items.append(PyEvalTrigger.model_validate(t))
                else:
                    # skip unsupported
                    continue
            store = cls(watchdog=items)
            return store
        except Exception as e:
            print(f"[Faust.backend.trigger_manager] Error loading triggers file: {e}")
            # create fresh store and overwrite corrupted file
            store = cls()
            store.save()
            return store


# module-level store
_store = TriggerStore.load()


def trigger_watchdog_thread_main(poll_interval: float = 0.5):
    while True:
        if exitflag:
            return # exit thread
        now = datetime.datetime.now()
        for trig in list(_store.watchdog):
            try:
                if trig.type == "datetime":
                    if now >= trig.target:
                        trigger_queue.put(trig.model_dump())
                        # remove one-time datetime trigger after firing
                        try:
                            _store.watchdog.remove(trig)
                            _store.save()
                        except Exception:
                            pass
                elif trig.type == "interval":
                    # trig is IntervalTrigger
                    if time.time() - trig.last_triggered >= trig.interval_seconds:
                        trigger_queue.put(trig.model_dump())
                        # update last_triggered
                        trig.last_triggered = time.time()
                        _store.save()
                elif trig.type == "py-eval":
                    try:
                        # evaluate; keep original behavior but catch exceptions
                        if eval(trig.eval_code):
                            trigger_queue.put(trig.model_dump())
                    except Exception as e:
                        print(f"[Faust.backend.trigger_manager] Error evaluating trigger {trig.id}: {e}")
                else:
                    # unknown type ignored
                    continue
            except Exception as e:
                print(f"[Faust.backend.trigger_manager] Watchdog loop error for trigger {getattr(trig,'id',None)}: {e}")
        time.sleep(poll_interval)
_thread=None
def start_trigger_watchdog_thread():
    global _thread
    _thread = threading.Thread(target=trigger_watchdog_thread_main, daemon=True)
    _thread.start()


def get_next_trigger(timeout: Optional[float] = None):
    try:
        return trigger_queue.get(timeout=timeout)
    except queue.Empty:
        return None


def append_trigger(trigger: dict | str):
    """Append a new trigger to the store.

    Supported trigger types are 'datetime', 'interval', and 'py-eval'.

    TRIGGER EXAMPLES:
    {
        "id": "datetime_trigger",
        "type": "datetime",
        "target": "2023-01-01T00:00:00Z"
    }
    
    {
        "id": "interval_trigger",
        "type": "interval",
        "interval_seconds": 3600
    }
    
    {
        "id": "py_eval_trigger",
        "type": "py-eval",
        "eval_code": "some_python_expression"
    }


    Args:
        trigger (dict): The trigger to append.

    Raises:
        ValueError: If the trigger type is unsupported or invalid.
    """    
    if isinstance(trigger, str):
        try:
            trigger = json.loads(trigger)
        except Exception as e:
            print(f"[Faust.backend.trigger_manager] Invalid trigger JSON string: {e}")
            raise
    global _store
    try:
        ttype = trigger.get("type")
        if ttype == "datetime":
            t = DateTimeTrigger.model_validate(trigger)
        elif ttype == "interval":
            t = IntervalTrigger.model_validate(trigger)
        elif ttype == "py-eval":
            t = PyEvalTrigger.model_validate(trigger)
        else:
            raise ValueError(f"Unsupported trigger type: {ttype}")
    except Exception as e:
        print(f"[Faust.backend.trigger_manager] Invalid trigger payload: {e}")
        raise
    
    # remove any existing with same id, then append & save
    try:
        _store.watchdog = [x for x in _store.watchdog if x.id != t.id]
        _store.watchdog.append(t)
        _store.save()
    except Exception as e:
        print(f"[Faust.backend.trigger_manager] Failed to append trigger: {e}")
        raise


def delete_trigger(trigger_id: str):
    global _store
    before = len(_store.watchdog)
    _store.watchdog = [t for t in _store.watchdog if t.id != trigger_id]
    if len(_store.watchdog) != before:
        try:
            _store.save()
        except Exception as e:
            print(f"[Faust.backend.trigger_manager] Failed to save after delete: {e}")


def get_trigger_information() -> str:
    # return formatted JSON of current store
    try:
        data = {"watchdog": [t.model_dump() for t in _store.watchdog]}
        return json.dumps(data, indent=4, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"[Faust.backend.trigger_manager] Failed to serialize triggers: {e}")
        return "{}"


def clear_triggers():
    global _store
    _store.watchdog.clear()
    try:
        _store.save()
    except Exception as e:
        print(f"[Faust.backend.trigger_manager] Failed to save after clear: {e}")
def has_queue_task():
    return not trigger_queue.empty()
if __name__ == "__main__":
    # test watchdog thread
    append_trigger({
        "id": "test_interval",
        "type": "interval",
        "interval_seconds": 5
    })
    append_trigger({
        "id": "test_datetime",
        "type": "datetime",
        "target": (datetime.datetime.now() + datetime.timedelta(seconds=10)).isoformat()
    })
    append_trigger({
        "id": "test_pyeval",
        "type": "py-eval",
        "eval_code": "random.random() < 0.1" 
    })
    start_trigger_watchdog_thread()
    print("Trigger watchdog thread started.")
    while True:
        trig = get_next_trigger(timeout=1.0)
        if trig:
            print("Trigger fired:", trig)
        else:
            print("No trigger fired in the last second.")