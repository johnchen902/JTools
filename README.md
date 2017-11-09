Sample usage:

```
#!/usr/bin/env python3
import asyncio
import sys
import jtools

args = jtools.create_argument_parser().parse_args()
logger = jtools.create_logger(args, __name__)

async def main():
    conn = await jtools.open_connection(args, logger)
    # ...
    print(*jtools.find_flags(await conn.read()))

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    sys.exit(loop.run_until_complete(main()))
```
