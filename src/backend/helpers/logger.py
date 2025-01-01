import logging
import os
import sys
import re
import time
from contextlib import contextmanager
from copy import copy
from typing import Callable

from termcolor import colored

LOG_LEVELS = ('CRITICAL', 'FATAL', 'ERROR', 'WARN', 'WARNING', 'INFO', 'DEBUG', 'NOTSET')


class NoColorFormatter(logging.Formatter):
    """
    Log formatter that strips terminal colour
    escape codes from the log message.
    """

    # Regex for ANSI colour codes
    ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

    def __init__(self):
        super().__init__()
        self.formatter = logging.Formatter('%(asctime)s.%(msecs)03d: %(message)s', '%m-%d %H:%M:%S')
        self.formatter.converter = time.gmtime

    def format(self, record: logging.LogRecord):
        """Return logger message with terminal escapes removed."""
        my_record = copy(record)
        my_record.msg = re.sub(self.ANSI_RE, "", str(my_record.msg))
        return self.formatter.format(my_record)


def create_logger():
    logger_ = logging.getLogger()
    logger_.handlers.clear()

    console_loglevel = 'INFO'

    formatter = logging.Formatter('%(asctime)s.%(msecs)03d: %(message)s', '%m-%d %H:%M:%S')
    formatter.converter = time.gmtime

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_loglevel)
    console_handler.setFormatter(formatter)
    logger_.addHandler(console_handler)

    # all messages DEBUG or higher will get passed to handlers, they can then decide using their loglevel
    logger_.setLevel(logging.DEBUG)
    # logger_.propagate = False
    return logger_


def set_logfile(
    logfile_name: str, file_loglevel: str = 'INFO', delete_existing_content: bool = False
):
    """
    Sets up the file logger to log to ../data/logs/{new_logfile_name}.log.
    Only one logfile will be in use any time. If you need to change the logfile,
    use change_logfile() instead.
    """
    global logger
    if len(logger.handlers) > 1:
        print("A logfile is already set! Leaving it as is.")
        return
    os.makedirs('../data/logs', exist_ok=True)
    file_handler = logging.FileHandler(filename=f'../data/logs/{logfile_name}.log')
    file_handler.setFormatter(NoColorFormatter())
    file_handler.setLevel(file_loglevel)
    logger.addHandler(file_handler)

    if delete_existing_content:
        reset_logfile()


def reset_logfile():
    """
    Truncates the current logfile to 0 bytes.
    """
    try:
        assert len(logger.handlers) == 2 and isinstance(logger.handlers[1], logging.FileHandler), 'file logger not present'
        os.truncate(logger.handlers[1].baseFilename, 0)
    except Exception as e:
        print(f'Could not reset logfile: {e}')


def change_logfile(new_logfile_name: str):
    """
    Direct all future logging into ../data/logs/{new_logfile_name}.log.
    """
    try:
        if len(logger.handlers) == 2 and isinstance(logger.handlers[1], logging.FileHandler):
            logger.removeHandler(logger.handlers[1])
        set_logfile(new_logfile_name)
    except Exception as e:
        print(f'Could not change logfile: {e}')


def _check_loglevel(level: str) -> None:
    assert level in LOG_LEVELS[:-1], f'Invalid log level: {level}'


def set_console_loglevel(level: str) -> None:
    """
    Sets console log level to specified level. Only messages with higher-or-equal priority to current level will get logged.
    Valid levels are (in decreasing priority): 'CRITICAL', 'FATAL', 'ERROR', 'WARN', 'WARNING', 'INFO', 'DEBUG'
    """
    _check_loglevel(level)
    if len(logger.handlers) >= 1 and isinstance(logger.handlers[0], logging.StreamHandler):
        logger.handlers[0].setLevel(level)


def set_file_loglevel(level: str) -> None:
    """
    Sets file log level to specified level. Only messages with higher-or-equal priority to current level  will get logged.
    Valid levels are (in decreasing priority): 'CRITICAL', 'FATAL', 'ERROR', 'WARN', 'WARNING', 'INFO', 'DEBUG'
    """
    _check_loglevel(level)
    if len(logger.handlers) == 2 and isinstance(logger.handlers[1], logging.FileHandler):
        logger.handlers[1].setLevel(level)


def log(*msg, level: str = 'INFO', color: str = None):
    if 'pytest' in sys.modules:
        # we're running in pytest, no need for logfiles (and coloring)
        if color:
            print(colored(*msg, color=color))
        else:
            print(*msg)
    else:
        str_msg = [str(item) for item in msg]
        final_msg = " ".join(str_msg)
        lines = final_msg.split('\n')
        for line in lines:
            if color:
                line = colored(line, color=color)
            getattr(logger, level.lower(), logger.debug)(msg=line)

def log_with_color_scale(*msg, value, thresholds: list[float], colors: list[str] = ('red', 'yellow', 'green'), level: str = 'DEBUG'):
    color = colors[-1]
    for threshold, color_ in zip(thresholds, colors):
        if value > threshold:
            color = color_
            break
    log(*msg, color=color, level=level)


def log_exception(e: Exception):
    logger.exception(e)


@contextmanager
def NoLog():
    """
    Context manager for completely disabling logging
    From https://gist.github.com/simon-weber/7853144
    """
    previous_level = logging.root.manager.disable
    logging.disable(logging.CRITICAL)

    try:
        yield
    finally:
        logging.disable(previous_level)


@contextmanager
def NoPrint():
    """
    Context manager for disabling console output. Output to file(s) still stay enabled.
    """

    def filter_(r):
        return False  # noqa

    console_handler = logger.handlers[0]
    console_handler.addFilter(filter_)

    try:
        yield
    finally:
        console_handler.removeFilter(filter_)


class CallbackLoggingHandler(logging.Handler):
    def __init__(self, callback: Callable, level=logging.DEBUG):
        super().__init__()
        self.callback = callback
        self.level = level
        self.formatter = NoColorFormatter()

    def emit(self, record):
        formatted = self.formatter.format(record)
        self.callback(formatted)


@contextmanager
def LogCallback(callback: Callable):
    clh = CallbackLoggingHandler(callback)
    logger.addHandler(clh)

    try:
        yield
    finally:
        logger.removeHandler(clh)


logger = create_logger()
