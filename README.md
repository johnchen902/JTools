Sample usage:

```
#!/usr/bin/env python3
import jtools

args = jtools.parse_args(description="Description")
with jtools.popen(args) as proc:
    pin, pout = jtools.stdio(args, proc)
    # Do something with pin, pout
```
