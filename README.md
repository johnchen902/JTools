Sample usage:

```
#!/usr/bin/python3
import asyncio
import sys
import jtools

args = jtools.create_argument_parser().parse_args()

async def main():
    r, w = await asyncio.open_connection(args.host, args.port)
    if args.verbose:
        r = jtools.ColorEchoStreamReader(r, data_color='light_green')
        w = jtools.ColorEchoStreamWriter(w, data_color='light_red')
    # ...
    print(*jtools.find_flags(await r.read()))

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    sys.exit(loop.run_until_complete(main()))
```
