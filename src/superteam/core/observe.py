from __future__ import annotations

from typing import Callable
import time

from .contracts import Event


class Observer:
    def __init__(
        self,
        session=None,
        stdout: bool = False,
        verbose: bool = False,
        hooks: list[Callable[[Event], None]] | None = None,
    ):
        self.session = session
        self.stdout = stdout
        self.verbose = verbose
        self.hooks = hooks or []

    def emit(self, event_type: str, payload: dict) -> Event | None:
        if event_type == "token" and not self.verbose:
            return None

        evt = Event(ts=time.time(), event=event_type, payload=payload)
        line = evt.to_jsonl()
        if self.session:
            self.session.append_event(line)
        if self.stdout:
            print(self.format_event(evt), flush=True)
        for hook in self.hooks:
            hook(evt)
        return evt

    @staticmethod
    def format_event(evt: Event) -> str:
        colors = {
            "step_start": "\033[36m",
            "output": "\033[32m",
            "verdict": "\033[33m",
            "loop_end": "\033[35m",
            "error": "\033[31m",
        }
        reset = "\033[0m"
        color = colors.get(evt.event, "\033[90m")
        ordered = [f"{key}={value}" for key, value in evt.payload.items()]
        return f"{color}[{evt.event}]{reset} {' | '.join(ordered)}".rstrip()
