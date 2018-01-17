"""Simple tools to play pwnable.
"""

__all__ = [
    'ASTConfigAction',
    'YAMLConfigAction',
    'create_logger',
    'open_connection',
    'Connection',
    'OffsetDict',
]

import argparse
import ast
import asyncio
import collections
import logging
import re
import sys
import types
import jtools.logger as jlogger

def argparse_update_config(parser, namespace, dest, new):
    """Internal method for updating config"""
    old = getattr(namespace, dest, None)
    if old is None:
        old = {}
    try:
        final = {**old, **new}
    except TypeError:
        parser.error("Config must be a mapping, not %s" % type(new).__name__)
    setattr(namespace, dest, final)

class ASTConfigAction(argparse.Action):
    """argparse.Action that parse a string with ast.literal_eval
       and merge resulting dictionary to destination"""
    def __call__(self, parser, namespace, values, option_string=None):
        argparse_update_config(parser, namespace, self.dest,
                               ast.literal_eval(values))

class YAMLConfigAction(argparse.Action):
    """argparse.Action that parse a string with yaml.safe_load
       and merge resulting dictionary to destination"""
    def __call__(self, parser, namespace, values, option_string=None):
        import yaml
        argparse_update_config(parser, namespace, self.dest,
                               yaml.safe_load(values))

def create_logger(args):
    """Create a jtools.logger.Logger described by args"""
    default_config = {
        'debug': {'max_indent': -1},
        'info': {'max_indent': -1, 'level': logging.INFO},
        'warn': {'level': logging.WARNING},
        'error': {'level': logging.ERROR},
        'open': {'max_indent': -1},
        'read': {'max_indent': -1},
        'write': {'max_indent': -1},
        'data': {'max_indent': -1},
    }
    event_config = args.config.get('events', default_config)

    logger = jlogger.Logger()
    logger.add_output(jlogger.TerminalOutput(event_config=event_config))
    logger.add_output(jlogger.LoggingOutput(logging.getLogger(__name__),
                                            event_config=event_config,
                                            default_level=logging.DEBUG))
    logger = logger.with_field('terminal_inhibited', [])
    return logger

async def open_connection(args):
    """Open a connection described by args.

    Returns a Connection decorated according to args.
    """

    logger = create_logger(args)

    reader, writer = await asyncio.open_connection(args.host, args.port)
    logger.log('open', 'open_connection(%s, %d)', args.host, args.port)

    old_feed_data = reader.feed_data
    def _new_feed_data(data):
        old_feed_data(data)
        logger.log('data', 'feed_data(%s)', data)
    reader.feed_data = _new_feed_data

    return Connection(reader, writer, logger)

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

    async def read(self, n=-1):
        """See `asyncio.StreamerReader.read`"""
        result = await self.reader.read(n)
        self.logger.log('read', 'read(%d) = %s', n, result)
        return result
    async def readline(self):
        """See `asyncio.StreamerReader.readline`"""
        result = await self.reader.readline()
        self.logger.log('read', 'readline() = %s', result)
        return result
    async def readexactly(self, n):
        """See `asyncio.StreamerReader.readexactly`"""
        result = await self.reader.readexactly(n)
        self.logger.log('read', 'readexactly(%d) = %s', n, result)
        return result
    async def readuntil(self, separator=b'\n'):
        """See `asyncio.StreamerReader.readuntil`"""
        result = await self.reader.readuntil(separator)
        self.logger.log('read', 'readuntil(%s) = %s', separator, result)
        return result

    def write(self, data):
        """See `asyncio.StreamerWriter.write`"""
        self.writer.write(data)
        self.logger.log('write', 'write(%s)', data)
    def writelines(self, data):
        """See `asyncio.StreamerWriter.writelines`"""
        self.writer.writelines(data)
        self.logger.log('write', 'writelines(%s)', data)
    def write_eof(self):
        """See `asyncio.StreamerWriter.write_eof`"""
        self.writer.write_eof()
        self.logger.log('write', 'write_eof()')

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

        self.logger.info('Entering interactive mode')
        self.logger.get_field('terminal_inhibited').append(None)
        await asyncio.wait({
            copy_forever(lambda: self.read(8192), transport.write),
            copy_forever(reader.readline, self.write),
            }, return_when=asyncio.FIRST_COMPLETED)
        self.logger.get_field('terminal_inhibited').pop()
        self.logger.info('Exited interactive mode')

    def with_logger(self, logger):
        """
        Create a copy of this connection with the logger replaced by `logger`.
        """
        return Connection(self.reader, self.writer, logger)

    def indent(self):
        """
        Create a copy of this connection with the indent of logger
        increased by 1.
        """
        indent = self.logger.get_field('indent', 0) + 1
        logger = self.logger.with_field('indent', indent)
        return self.with_logger(logger)

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
