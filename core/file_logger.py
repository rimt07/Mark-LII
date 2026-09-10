"""
Rolling file logger for MARK LII.

Captures everything the app writes to stdout and stderr — print()s, tracebacks,
library warnings, the [MCP]/[Ollama]/[Audio] status lines — into a rotating log
file so a crash or a "why didn't it speak?" can be inspected after the fact,
even when the app was launched windowless via pythonw (where stdout goes
nowhere) or the on-screen console has already trimmed old lines.

Design:
- It TEES: each write goes to the ORIGINAL stream first (so the terminal and the
  UI's own ConsoleRedirector keep working exactly as before) and then to the log
  file. Installing this must not remove existing behaviour.
- Rotation is handled by the stdlib RotatingFileHandler: 5 MB per file, a few
  backups (jarvis.log, jarvis.log.1, …). No unbounded growth.
- It never raises out of write()/flush(): a logging failure must never take the
  app down, which is the whole reason this exists.

Usage (call ONCE, as early as possible in main.py):

    from core.file_logger import install_file_logging
    install_file_logging(BASE_DIR / "logs" / "jarvis.log")
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Module-level guard so a second import / re-entry can't double-wrap the streams
# (which would double every line in the file).
_installed = False
_handler: Optional[RotatingFileHandler] = None


class _TeeStream:
    """
    Wraps a real stream (sys.stdout or sys.stderr) and mirrors every write into
    a logging channel, while still forwarding to the original stream. Presents
    the file-like surface (write/flush/fileno/isatty/encoding/…) that libraries
    and subprocess plumbing probe, delegating all of it to the original so
    nothing downstream can tell it was wrapped.
    """

    def __init__(self, original, log_fn):
        self._original = original
        self._log_fn = log_fn          # callable(str) -> None, writes to the file
        self._buffer = ""              # accumulates partial lines until newline

    # -- the two methods that matter --
    def write(self, text):
        # Forward to the real stream first so normal output is never delayed or
        # lost if the file side misbehaves.
        if self._original is not None:
            try:
                self._original.write(text)
            except Exception:
                pass
        # Mirror to the log file, line-buffered so the file has clean lines and
        # we don't emit a log record per character.
        try:
            if text:
                self._buffer += text
                while "\n" in self._buffer:
                    line, self._buffer = self._buffer.split("\n", 1)
                    self._log_fn(line)
        except Exception:
            pass
        return len(text) if text else 0

    def flush(self):
        # Emit any trailing partial line, then flush the real stream.
        try:
            if self._buffer:
                self._log_fn(self._buffer)
                self._buffer = ""
        except Exception:
            pass
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass

    # -- transparent delegation for everything a stream is expected to expose --
    def fileno(self):
        if self._original is not None and hasattr(self._original, "fileno"):
            return self._original.fileno()
        raise OSError("no fileno on wrapped stream")

    def isatty(self):
        try:
            return bool(self._original and self._original.isatty())
        except Exception:
            return False

    @property
    def encoding(self):
        return getattr(self._original, "encoding", "utf-8")

    @property
    def errors(self):
        return getattr(self._original, "errors", "replace")

    @property
    def closed(self):
        try:
            return bool(self._original and self._original.closed)
        except Exception:
            return False

    def writable(self):
        return True

    # Expose the underlying real stream, mirroring ConsoleRedirector.original,
    # so code that unwraps to reach a real fd (e.g. MCP's stdio errlog resolver)
    # keeps working.
    @property
    def original(self):
        return self._original


def install_file_logging(
    log_path,
    max_bytes: int = 5 * 1024 * 1024,   # 5 MB per file
    backup_count: int = 3,
) -> Optional[Path]:
    """
    Tee sys.stdout and sys.stderr into a rotating log file. Idempotent: a second
    call is a no-op. Returns the log path on success, None if logging could not
    be set up (in which case stdout/stderr are left untouched).
    """
    global _installed, _handler
    if _installed:
        return Path(log_path)

    try:
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        # Plain message layout with a timestamp; the app already tags its own
        # lines ([MCP], [Ollama], …) so we don't repeat a logger name.
        handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

        logger = logging.getLogger("jarvis.console")
        logger.setLevel(logging.INFO)
        logger.propagate = False       # don't also hit the root logger
        # Clear any handlers from a previous partial install.
        for h in list(logger.handlers):
            logger.removeHandler(h)
        logger.addHandler(handler)

        def _log_line(line: str):
            # Skip truly empty lines so the file isn't padded with blank records,
            # but keep whitespace-only lines that carry layout.
            if line != "":
                logger.info(line)
                # Flush immediately: this log's whole purpose is post-mortem
                # inspection, so a line must survive an abrupt kill/crash rather
                # than sit in a buffer that never gets flushed.
                try:
                    handler.flush()
                except Exception:
                    pass

        sys.stdout = _TeeStream(sys.stdout, _log_line)
        sys.stderr = _TeeStream(sys.stderr, _log_line)

        _handler = handler
        _installed = True

        # First line so every run is delimited in the file.
        logger.info("──────── MARK LII session start — logging to %s (%.0f MB rolling) ────────"
                     % (log_path, max_bytes / (1024 * 1024)))
        return log_path
    except Exception as e:
        # Never fatal — if logging can't be set up, the app runs exactly as it
        # did before this feature existed.
        try:
            sys.__stderr__.write(f"[file_logger] disabled: {e}\n")
        except Exception:
            pass
        return None
