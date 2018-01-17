"""
Custom logger.

+ Each entries have an 'event' tag
+ Designed for terminal output
+ Indention
+ Filter by event and indention
+ Limit length of each line
+ Colorize by event
+ Interactive mode (inhibiting terminal output)
+ Can output to other loggers
"""
import os
import sys
import traceback

class Logger:
    """
    The custom logger. It can:
    + Add outputs (e.g. TerminalOutput)
    + Maintain immutable fields
    + Log events
    """

    def __init__(self):
        self._outputs = []
        self._fields = {}

    def log(self, event, msg, *args):
        """
        Logs a message with event 'event' on this logger.
        The 'msg' is the message format string,
        and the 'args' are the arguments which are merged
        into 'msg' using the string formatting operator.
        """
        for output in self._outputs:
            try:
                output(self._fields, event, msg, *args)
            except Exception:
                print(traceback.format_exc(), file=sys.stderr)

    def debug(self, msg, *args):
        """Shortcut of log('debug', msg, *args)"""
        self.log('debug', msg, *args)
    def info(self, msg, *args):
        """Shortcut of log('info', msg, *args)"""
        self.log('info', msg, *args)
    def warn(self, msg, *args):
        """Shortcut of log('warn', msg, *args)"""
        self.log('warn', msg, *args)
    def error(self, msg, *args):
        """Shortcut of log('error', msg, *args)"""
        self.log('error', msg, *args)

    def add_output(self, output):
        """
        Add an output to this logger.
        It should be a callable with arguments (fields, event, msg, *args);
        see TerminalOutput for example.
        """
        self._outputs.append(output)

    def with_field(self, key, value):
        """
        Create a copy of this logger with the field `key` replaced by `value`.
        The underlying outputs is shared (not copied).
        """
        logger = Logger()
        logger._outputs = self._outputs
        logger._fields = {**self._fields, key: value}
        return logger

    def get_field(self, key, default=None):
        """Get a value of field `key` with default `default`."""
        return self._fields.get(key, default)

class TerminalOutput:
    """
    The terminal output. It can:

    + Inhibit all outputs on request (e.g. interactive mode)
    + Filter on events and indentions.
    + Indent lines.
    + Limit length of each line.
    + Colorize output by events.
    """

    def __init__(self, stream=sys.stderr, event_config=None):
        self._stream = stream
        self.event_config = event_config if event_config is not None else {}
        self.indent_str = ' ' * 4

    def _fit_line(self, message, prefix, suffix):
        # How to calculate length properly?
        columns = os.get_terminal_size(self._stream.fileno()).columns
        if len(prefix) + len(message) + len(suffix) > columns:
            shorten_to = max(23, columns - len(prefix) - len(suffix))
            len1 = (shorten_to - 2) // 2
            len2 = (shorten_to - 3) // 2
            message = message[:len1] + '...' + message[-len2:]
        return prefix + message + suffix

    def __call__(self, fields, event, msg, *args):
        if fields.get('terminal_inhibited', False):
            return

        config = self.event_config.get(event, {})
        indent = fields.get('indent', 0)
        max_indent = config.get('max_indent', None)
        if max_indent is not None and indent > max_indent:
            return

        message = msg % args
        prefix = self.indent_str * indent + config.get('prefix', '')
        suffix = config.get('suffix', '')

        message = self._fit_line(message, prefix, suffix)

        self._stream.write(message + '\n')
        self._stream.flush()

class LoggingOutput:
    """Output to logging"""
    def __init__(self, logger, event_config=None, *, default_level=0):
        self.logger = logger
        self.event_config = event_config if event_config is not None else {}
        self.default_level = default_level
    def __call__(self, fields, event, msg, *args):
        config = self.event_config.get(event, {})
        level = config.get('level', self.default_level)
        self.logger.log(level, msg, *args, extra=fields)
