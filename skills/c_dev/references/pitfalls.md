# Common C Pitfalls

## Memory

| Bug | Symptom | Check |
|-----|---------|-------|
| Off-by-one on a buffer | Corrupted neighbouring variable, crash later | Does the size include the `\0`? |
| Use after free | Random garbage, works in debug builds | Set pointers to `NULL` after `free` |
| Double free | Crash inside `free` | Every allocation freed on exactly one path |
| Leak on an error path | Memory grows over time | Does every early `return` free what it owns? |

## Strings

- `strlen` does not count the `\0`, so allocate `strlen(s) + 1`.
- `strncpy` does not add a `\0` when the source is too long. Terminate it yourself.
- `snprintf` returns the length it *wanted* to write, which can exceed the buffer.

## Integers

- Signed overflow is undefined behaviour; the compiler may delete your check.
- Compare sizes with `size_t`, not `int`. `i < len` with a signed `i` warns for a reason.
- `char` may be signed or unsigned. Cast to `unsigned char` before calling `isalpha` and friends.

## Debugging

1. Rebuild with `-g -fsanitize=address,undefined`. This finds most memory bugs at once.
2. If it only crashes without the sanitizer, suspect uninitialised memory.
3. If it only crashes with optimisation on, suspect undefined behaviour.
