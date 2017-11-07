"""Simple tools to play pwnable.
"""

__all__ = [
    'create_argument_parser',
    'find_flags',
    'open_connection',
    'Connection',
    'EchoStreamReader',
    'EchoStreamWriter',
    'ColorEchoStreamReader',
    'ColorEchoStreamWriter',
    'OffsetDict',
]

import argparse
import asyncio
import collections
import itertools
import re
import sys
import colored

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

async def open_connection(args):
    """Open a connection described by args.

    Returns a Connection decorated according to args.
    Such connection is not exactly a (reader, writer) pair,
    but can be used as:

    >>> reader, writer = await open_connection(args)
    """
    reader, writer = await asyncio.open_connection(args.host, args.port)
    if args.verbose:
        if should_colorize(args):
            # TODO Configure color.
            reader = ColorEchoStreamReader(reader, data_color='light_green')
            writer = ColorEchoStreamWriter(writer, data_color='light_red')
        else:
            reader = EchoStreamReader(reader)
            writer = EchoStreamWriter(writer)
    return Connection(reader, writer)

def find_flags(flagdata):
    """Returns flags of form FLAG{[^}]+} found in flagdata."""
    if isinstance(flagdata, bytes):
        return re.findall(b'FLAG{[^}]+}', flagdata)
    return re.findall('FLAG{[^}]+}', str(flagdata))

def format_function_call(name, *args, **kwargs):
    """Returns name(arg0, ..., kw0=kwarg0, ...)"""
    return '%s(%s)' % (name, ', '.join(
        itertools.chain((str(a) for a in args),
                        ('%s=%s' % i for i in kwargs.items()))))

class Connection:
    """A wrapper of plain (reader, writer) pair"""
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
    def __iter__(self):
        yield self.reader
        yield self.writer
    async def read(self, n=-1):
        """See `asyncio.StreamerReader.read`"""
        return await self.reader.read(n)
    async def readline(self):
        """See `asyncio.StreamerReader.readline`"""
        return await self.reader.readline()
    async def readexactly(self, n):
        """See `asyncio.StreamerReader.readexactly`"""
        return await self.reader.readexactly(n)
    async def readuntil(self, separator=b'\n'):
        """See `asyncio.StreamerReader.readuntil`"""
        return await self.reader.readuntil(separator)
    def write(self, data):
        """See `asyncio.StreamerWriter.write`"""
        self.writer.write(data)
    def writelines(self, data):
        """See `asyncio.StreamerWriter.writelines`"""
        self.writer.writelines(data)
    def write_eof(self):
        """See `asyncio.StreamerWriter.write_eof`"""
        self.writer.write_eof()

class EchoStreamReader:
    """Wrapper around asyncio.StreamReader recording read* calls."""
    def __init__(self, reader, output=sys.stdout):
        """
        Arguments:
            - reader -- wrapped asyncio.StreamReader
            - output -- stream to echo to (default: sys.stdout)
        """
        self._reader = reader
        self._output = output
    def __getattr__(self, attr):
        orig_attr = self._reader.__getattribute__(attr)
        if callable(orig_attr) and self.is_read_function(attr):
            if asyncio.iscoroutinefunction(orig_attr):
                async def _hooked_coroutine(*args, **kwargs):
                    self.echo_function(attr, *args, **kwargs)
                    result = await orig_attr(*args, **kwargs)
                    self.echo_data(result)
                    return result
                return _hooked_coroutine
            def _hooked(*args, **kwargs):
                self.echo_function(attr, *args, **kwargs)
                result = orig_attr(*args, **kwargs)
                self.echo_data(result)
                return result
            return _hooked
        return orig_attr
    @staticmethod
    def is_read_function(funcname):
        """Returns true if funcname is a read* and thus should be recorded."""
        return funcname.startswith('read')
    def echo_function(self, funcname, *args, **kwargs):
        """Record the function name and argument being called."""
        self._output.write('%s = ' % format_function_call(funcname, *args, **kwargs))
        self._output.flush()
    def echo_data(self, data):
        """Record return value."""
        self._output.write('%r\n' % data)
        self._output.flush()

class EchoStreamWriter:
    """Wrapper around asyncio.StreamWriter recording write* calls."""
    def __init__(self, writer, output=sys.stdout):
        self._writer = writer
        self._output = output
    def __getattr__(self, attr):
        orig_attr = self._writer.__getattribute__(attr)
        if callable(orig_attr) and self.is_write_attr(attr):
            if asyncio.iscoroutinefunction(orig_attr):
                async def _hooked_coroutine(*args, **kwargs):
                    self.echo_function(attr, *args, **kwargs)
                    return await orig_attr(*args, **kwargs)
                return _hooked_coroutine
            def _hooked(*args, **kwargs):
                self.echo_function(attr, *args, **kwargs)
                return orig_attr(*args, **kwargs)
            return _hooked
        return orig_attr
    @staticmethod
    def is_write_attr(attr):
        """Returns true if funcname is a write* and thus should be recorded."""
        return attr.startswith('write')
    def echo_function(self, attr, *args, **kwargs):
        """Record the function name and argument being called."""
        self._output.write('%s\n' % format_function_call(attr, *args, **kwargs))
        self._output.flush()

class ColorEchoStreamReader(EchoStreamReader):
    """An EchoStreamReader that add colors."""
    def __init__(self, reader, output=sys.stdout, header_color=None, data_color=None):
        """
        Arguments:
            - reader -- wrapped asyncio.StreamReader
            - output -- stream to echo to (default: sys.stdout)
            - header_color -- colored.fg compatible color
            - data_color -- colored.fg compatible color
        """
        super().__init__(reader, output)
        self._header_color = header_color
        self._data_color = data_color
    def echo_function(self, funcname, *args, **kwargs):
        funccall = format_function_call(funcname, *args, **kwargs)
        if self._header_color is not None:
            funccall = colored.stylize(funccall, colored.fg(self._header_color))
        self._output.write('%s = ' % funccall)
        self._output.flush()
    def echo_data(self, data):
        data = repr(data)
        if self._data_color is not None:
            data = colored.stylize(data, colored.fg(self._data_color))
        self._output.write('%s\n' % data)
        self._output.flush()

class ColorEchoStreamWriter(EchoStreamWriter):
    """An EchoStreamWriter that add colors."""
    def __init__(self, writer, output=sys.stdout, header_color=None, data_color=None):
        """
        Arguments:
            - reader -- wrapped asyncio.StreamReader
            - output -- stream to echo to (default: sys.stdout)
            - header_color -- colored.fg compatible color
            - data_color -- colored.fg compatible color
        """
        super().__init__(writer, output)
        self._header_color = header_color
        self._data_color = data_color
    def echo_function(self, attr, *args, **kwargs):
        if self._header_color is not None:
            attr = colored.stylize(attr, colored.fg(self._header_color))
        if self._data_color is not None and len(args) >= 1:
            colored_arg0 = colored.stylize(args[0], colored.fg(self._data_color))
            args = (colored_arg0,) + args[1:]
        self._output.write('%s\n' % format_function_call(attr, *args, **kwargs))
        self._output.flush()

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
