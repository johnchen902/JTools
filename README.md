Sample usage:

```
#!/usr/bin/env python3
import asyncio
import sys
import jtools

args = jtools.create_argument_parser().parse_args()

async def main():
    r, w = await jtools.open_connection(args)
    # ...
    print(*jtools.find_flags(await r.read()))

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    sys.exit(loop.run_until_complete(main()))
```
