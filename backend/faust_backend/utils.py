import functools
import inspect
def show_return_wrapper(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        result = await func(*args, **kwargs)
        print(f"Returning from {func.__name__}:", result)
        return result
    try:
        wrapper.__signature__ = inspect.signature(func)
    except Exception:
        pass
    return wrapper
