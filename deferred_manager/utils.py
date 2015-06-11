import types
import os
import operator

from google.appengine.api import queueinfo


def get_func_repr(func):
    if isinstance(func, types.MethodType):
        return "{cls}.{func}".format(
            cls=func.im_self.__class__,
            func=func.im_func.__name__
        )
    elif isinstance(func, types.BuiltinMethodType):
        if not func.__self__:
            return "{func}".format(
                func=func.__name__
            )
        else:
            return "{type}.{func}".format(
                type=func.__self__,
                func=func.__name__
            )
    elif (isinstance(func, types.ObjectType) and hasattr(func, "__call__")) or\
        isinstance(func, (types.FunctionType, types.BuiltinFunctionType,
                        types.ClassType, types.UnboundMethodType)):
        return "{module}.{func}".format(
            module=func.__module__,
            func=func.__name__
        )
    else:
        raise ValueError("func must be callable")


def strip_defer_kwargs(kwargs):
    return {k:v for k, v in kwargs.items() if not k.startswith('_')}


def get_defer_kwargs(kwargs):
    return {k:v for k, v in kwargs.items() if k.startswith('_')}


def get_queue_info():
    """
    Retrieve queue.yaml file
    """
    directory = os.environ.get(
        'DEFERRED_MANAGER_ROOT_DIR', os.path.abspath("."))

    while directory:
        file_path = os.path.join(directory, 'queue.yaml')
        if os.path.isfile(file_path):
            with open(file_path, 'r') as fh:
                return queueinfo.LoadSingleQueue(fh)
        else:
            directory = os.path.dirname(directory)
            if os.path.realpath(directory) == directory:
                break

def attrgetter(attr, default=None):
    def _inner(obj):
        try:
            return operator.attrgetter(attr)(obj)
        except AttributeError:
            return default
    return _inner
