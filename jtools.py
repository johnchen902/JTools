"""Simple tools to play pwnable.
"""

__all__ = [
    'create_argument_parser',
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

def create_handler(config):
    """Create a logging.Handler as specified"""
    if config.filename is None:
        handler = logging.StreamHandler()
    else:
        handler = logging.FileHandler(config.filename)
    handler.setFormatter(logging.Formatter(fmt=config.format))
    handler.setLevel(config.level)
    return handler

class LogArgumentParser(argparse.ArgumentParser):
    """Internal class for parsing --log."""
    def __init__(self, parent):
        super().__init__(prog='--log', add_help=False, description="""
            Contrary to what this help message suggested,
            --log only accepts comma-separated suboptions.
            Some suboptions may include an associated value,
            which is separated from the suboption name by an equal sign.
            This is an example (and the default): 'info'.
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

        result = types.SimpleNamespace()
        result.filename = args.file
        result.format = args.format
        result.level = getattr(logging, args.level.upper())
        return result
    return _parse_log_handler

def create_logger(args, name):
    """Create a logger with specified name, and configure it according to args"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    # args.log_handlers may be None
    if args.log_handlers:
        for config in args.log_handlers:
            logger.addHandler(create_handler(config))
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

async def copy_forever(input_func, output_func):
    """Internal function; see implementation"""
    while True:
        data = await input_func()
        if not data:
            break
        output_func(data)

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
    def _debug(self, *args, **kwargs):
        self.logger.debug(*args, **kwargs)
    async def read(self, n=-1):
        """See `asyncio.StreamerReader.read`"""
        result = await self.reader.read(n)
        self._debug('read(%d) = %s', n, result)
        return result
    async def readline(self):
        """See `asyncio.StreamerReader.readline`"""
        result = await self.reader.readline()
        self._debug('readline() = %s', result)
        return result
    async def readexactly(self, n):
        """See `asyncio.StreamerReader.readexactly`"""
        result = await self.reader.readexactly(n)
        self._debug('readexactly(%d) = %s', n, result)
        return result
    async def readuntil(self, separator=b'\n'):
        """See `asyncio.StreamerReader.readuntil`"""
        result = await self.reader.readuntil(separator)
        self._debug('readuntil(%s) = %s', separator, result)
        return result
    def write(self, data):
        """See `asyncio.StreamerWriter.write`"""
        self._debug('write(%s)', data)
        self.writer.write(data)
    def writelines(self, data):
        """See `asyncio.StreamerWriter.writelines`"""
        self._debug('writelines(%s)', data)
        self.writer.writelines(data)
    def write_eof(self):
        """See `asyncio.StreamerWriter.write_eof`"""
        self._debug('write_eof()')
        self.writer.write_eof()
    async def interact(self, *, pipe_in=sys.stdin, pipe_out=sys.stdout):
        """Interactive mode.

        It does this two things until either EOF is received.
        1. Copy data from self.reader to pipe_out.
        2. Copy data from pipe_in to self.writer.
        """
        loop = asyncio.get_event_loop()

        reader = asyncio.StreamReader()
        await loop.connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader), pipe_in)
        transport, _ = await loop.connect_write_pipe(
            asyncio.BaseProtocol, pipe_out)

        await asyncio.wait({
            copy_forever(lambda: self.read(8192), transport.write),
            copy_forever(reader.readline, self.write),
            }, return_when=asyncio.FIRST_COMPLETED)

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
