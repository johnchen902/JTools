"""Simple tools to play pwnable.
"""

__all__ = [
    'create_argument_parser',
    'find_flags',
    'EchoStreamReader',
    'EchoStreamWriter',
    'ColorEchoStreamReader',
    'ColorEchoStreamWriter',
]

import argparse
import asyncio
import itertools
import re
import sys
import colored

def create_argument_parser(**kwargs):
    """Create an argparse.ArgumentParser whose result can be used by jtools.

    Arguments are directly forwarded to argparse.ArgumentParser.
    """
    parser = argparse.ArgumentParser(**kwargs)
    parser.add_argument(
        '-v', '--verbose', action='store_true', help='log data sent/received')
    parser.add_argument('host')
    parser.add_argument('port', type=int)
    return parser

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
    def echo_data(self, data):
        """Record return value."""
        self._output.write('%r\n' % data)

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
    def echo_data(self, data):
        data = repr(data)
        if self._data_color is not None:
            data = colored.stylize(data, colored.fg(self._data_color))
        self._output.write('%s\n' % data)

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
