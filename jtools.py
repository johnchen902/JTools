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
        '-v', '--verbose', action='store_true',
        help='log data sent and received')
    parser.add_argument(
        '--color', metavar='WHEN', choices=['always', 'auto', 'never'],
        nargs='?', default='never', const='always',
        help="""colorize the output;
                WHEN can be 'always' (default if omitted), 'auto', or 'never'""")
    return parser

def should_colorize(args):
    """Determine if we should colorize the output"""
    if args.color == 'always':
        return True
    if args.color == 'never':
        return False
    if args.color == 'auto':
        return sys.stdout.isatty()
    raise ValueError('Bad args.color')

REGEX_READ = re.compile('(read.* = )%s')
REGEX_WRITE = re.compile(r'(write.*)\((.+)\)')
def msg_color_filter(msg):
    """filter supporting --color (str to str)"""
    match = REGEX_READ.fullmatch(msg)
    if match:
        # TODO config colors
        return match.expand('\\1\033[38;5;10m%s\033[0m')
    match = REGEX_WRITE.fullmatch(msg)
    if match:
        return match.expand('\\1(\033[38;5;9m\\2\033[0m)')
    return msg
def color_filter(record):
    """filter supporting --color (logging interface)"""
    record.msg = msg_color_filter(str(record.msg))
    return True

def create_logger(args, name):
    """Create a logger with specified name, and configure it according to args"""
    logger = logging.getLogger(name)
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())
    if should_colorize(args):
        logger.addFilter(color_filter)
    return logger

async def open_connection(args, logger=None):
    """Open a connection described by args.

    Returns a Connection decorated according to args.
    Such connection is not exactly a (reader, writer) pair,
    but can be used as:

    >>> reader, writer = await open_connection(args)
    """

    if logger is None:
        logger = types.SimpleNamespace(debug=lambda *args, **kwargs: None)

    reader, writer = await asyncio.open_connection(args.host, args.port)
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
    async def read(self, n=-1):
        """See `asyncio.StreamerReader.read`"""
        result = await self.reader.read(n)
        self.logger.debug('read(%d) = %s', n, result)
        return result
    async def readline(self):
        """See `asyncio.StreamerReader.readline`"""
        result = await self.reader.readline()
        self.logger.debug('readline() = %s', result)
        return result
    async def readexactly(self, n):
        """See `asyncio.StreamerReader.readexactly`"""
        result = await self.reader.readexactly(n)
        self.logger.debug('readexactly(%d) = %d', n, result)
        return result
    async def readuntil(self, separator=b'\n'):
        """See `asyncio.StreamerReader.readuntil`"""
        result = await self.reader.readuntil(separator)
        self.logger.debug('readuntil(%s) = %s', separator, result)
        return result
    def write(self, data):
        """See `asyncio.StreamerWriter.write`"""
        self.logger.debug('write(%s)', data)
        self.writer.write(data)
    def writelines(self, data):
        """See `asyncio.StreamerWriter.writelines`"""
        self.logger.debug('writelines(%s)', data)
        self.writer.writelines(data)
    def write_eof(self):
        """See `asyncio.StreamerWriter.write_eof`"""
        self.logger.debug('write_eof()')
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
