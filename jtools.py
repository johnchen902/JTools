"""Simple tools to play pwnable.
"""

__all__ = [
    'create_argument_parser',
    'HandlerConfig',
    'find_flags',
    'create_logger',
    'open_connection',
    'Connection',
    'OffsetDict',
]

import argparse
import asyncio
import collections
import logging
import re
import sys
import types

def create_argument_parser(**kwargs):
    """Create an argparse.ArgumentParser whose result can be used by jtools.

    Arguments are directly forwarded to argparse.ArgumentParser.
    """
    parser = argparse.ArgumentParser(**kwargs)
    parser.add_argument('host')
    parser.add_argument('port', type=int)
    parser.add_argument(
        '--log', metavar='LOG', action='append', type=create_log_parser(parser),
        nargs='?', const='', dest='log_handlers',
        help="Add a log handler. See `--log help` for detail.")
    return parser

class HandlerConfig(types.SimpleNamespace):
    """Data struture used by --log"""
    def create_handler(self):
        """Create a logging.Handler as specified"""
        if self.filename is None:
            handler = logging.StreamHandler()
        else:
            handler = logging.FileHandler(self.filename)
        if self.should_colorize():
            # TODO configure ColorFormatter rule
            handler.setFormatter(ColorFormatter(fmt=self.format))
        else:
            handler.setFormatter(logging.Formatter(fmt=self.format))
        handler.setLevel(self.level)
        return handler
    def should_colorize(self):
        """Determine if we should colorize the output"""
        if self.color == 'always':
            return True
        if self.color == 'never':
            return False
        if self.color == 'auto':
            return self.filename is None and sys.stderr.isatty()
        raise ValueError('Bad color')

class LogArgumentParser(argparse.ArgumentParser):
    """Internal class for parsing --log."""
    def __init__(self, parent):
        super().__init__(prog='--log', add_help=False, description="""
            Contrary to what this help message suggested,
            --log only accepts comma-separated suboptions.
            Some suboptions may include an associated value,
            which is separated from the suboption name by an equal sign.
            This is an example (and the default): 'color=never,info'.
        """)
        self._parent = parent
    def error(self, message):
        raise argparse.ArgumentTypeError(message)
    def exit(self, status=0, message=None):
        self._parent.exit(status, message)

def create_log_parser(parent):
    """Internal function for parsing --log; returns str->HandlerConfig"""
    parser = LogArgumentParser(parent)
    parser.add_argument(
        '--help', action='help',
        help="show this help message and exit")

    parser.add_argument(
        '--file',
        help="write to FILE instead of standard error")

    parser.add_argument(
        '--format', default='%(message)s',
        help="change log format (See logging.Formatter)")

    parser.add_argument(
        '--color', choices=['always', 'auto', 'never'],
        nargs='?', default='never', const='always',
        help="colorize the output")

    log_levels = ['debug', 'info', 'warning', 'error']
    levelgroup = parser.add_mutually_exclusive_group()
    levelgroup.add_argument(
        '--level', choices=log_levels, default='info',
        help="set logging level")
    for level in log_levels:
        levelgroup.add_argument(
            '--%s' % level, dest='level', action='store_const', const=level,
            help="equivalent to --level=%s" % level)

    def _parse_log_handler(argstr):
        arglist = ['--%s' % s for s in argstr.split(',') if s]
        args = parser.parse_args(arglist)

        result = HandlerConfig()
        result.filename = args.file
        result.format = args.format
        result.color = args.color
        result.level = getattr(logging, args.level.upper())
        return result
    return _parse_log_handler

class ColorFormatter(logging.Formatter):
    """Formatter supporting --log color"""
    DEFAULT_RULES = [
        (re.compile('(read.* = )(%s)'), '\\1\033[38;5;10m\\2\033[0m'),
        (re.compile(r'(write.*)\((.+)\)'), '\\1(\033[38;5;9m\\2\033[0m)'),
    ]
    def __init__(self, *, rules=None, **kwargs):
        super().__init__(**kwargs)
        if rules is None:
            rules = ColorFormatter.DEFAULT_RULES
        self._rules = rules
    def format(self, record):
        old_msg = record.msg
        record.msg = self._colorize_msg(str(record.msg))
        try:
            return super().format(record)
        finally:
            record.msg = old_msg
    def _colorize_msg(self, msg):
        for pattern, replacement in self._rules:
            match = pattern.fullmatch(msg)
            if match:
                return match.expand(replacement)
        return msg

def create_logger(args, name):
    """Create a logger with specified name, and configure it according to args"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    # args.log_handlers may be None
    if args.log_handlers:
        for config in args.log_handlers:
            logger.addHandler(config.create_handler())
    return logger

async def open_connection(args, logger):
    """Open a connection described by args.

    Returns a Connection decorated according to args.
    """
    if not logger:
        raise ValueError('logger is falsy')

    reader, writer = await asyncio.open_connection(args.host, args.port)

    old_feed_data = reader.feed_data
    def _new_feed_data(data):
        old_feed_data(data)
        logger.debug('feed_data(%s)', data)
    reader.feed_data = _new_feed_data

    return Connection(reader, writer, logger)

def find_flags(flagdata):
    """Returns flags of form FLAG{[^}]+} found in flagdata."""
    if isinstance(flagdata, bytes):
        return re.findall(b'FLAG{[^}]+}', flagdata)
    return re.findall('FLAG{[^}]+}', str(flagdata))

class Connection:
    """Returned by open_connection."""
    def __init__(self, reader, writer, logger):
        """Don't call it directly."""
        self.reader = reader
        self.writer = writer
        self.logger = logger
    def __iter__(self):
        yield self.reader
        yield self.writer
    def _info(self, *args, **kwargs):
        self.logger.info(*args, **kwargs)
    async def read(self, n=-1):
        """See `asyncio.StreamerReader.read`"""
        result = await self.reader.read(n)
        self._info('read(%d) = %s', n, result)
        return result
    async def readline(self):
        """See `asyncio.StreamerReader.readline`"""
        result = await self.reader.readline()
        self._info('readline() = %s', result)
        return result
    async def readexactly(self, n):
        """See `asyncio.StreamerReader.readexactly`"""
        result = await self.reader.readexactly(n)
        self._info('readexactly(%d) = %s', n, result)
        return result
    async def readuntil(self, separator=b'\n'):
        """See `asyncio.StreamerReader.readuntil`"""
        result = await self.reader.readuntil(separator)
        self._info('readuntil(%s) = %s', separator, result)
        return result
    def write(self, data):
        """See `asyncio.StreamerWriter.write`"""
        self._info('write(%s)', data)
        self.writer.write(data)
    def writelines(self, data):
        """See `asyncio.StreamerWriter.writelines`"""
        self._info('writelines(%s)', data)
        self.writer.writelines(data)
    def write_eof(self):
        """See `asyncio.StreamerWriter.write_eof`"""
        self._info('write_eof()')
        self.writer.write_eof()

class OffsetDict(collections.MutableMapping):
    """A mutable mapping of which values have fixed offsets.

    When modifying value of an existing key,
    the base will be modified instead.
    """

    __slots__ = ('_base', '_dict')

    def __init__(self, *args, _base=None, **kwargs):
        self._base = _base
        self._dict = dict(*args, **kwargs)

    def __len__(self):
        return len(self._dict)

    def __iter__(self):
        return iter(self._dict)

    def __getitem__(self, key):
        value = self._dict[key]
        if self._base is None:
            return value
        return self._base + value

    def __setitem__(self, key, value):
        if key in self._dict:
            self._base = value - self._dict[key]
        elif self._base is None:
            self._dict[key] = value
        else:
            self._dict[key] = value - self._base

    def __delitem__(self, key):
        del self._dict[key]
