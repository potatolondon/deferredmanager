import logging

from google.appengine.ext import ndb, deferred

from .models import TaskState, UniqueTaskMarker
from .utils import strip_defer_kwargs, get_func_repr, get_defer_kwargs


@ndb.transactional(xg=True)
def defer(obj, *args, **kwargs):
    from .handler import task_wrapper

    unique = kwargs.pop('unique', False)
    task_reference = kwargs.pop('task_reference', None)

    if unique:
        assert task_reference, "a task_reference must be passed"

        if UniqueTaskMarker.get_by_id(task_reference):
            logging.warning(
                "Did not defer task with reference {0} - task already present".format(task_reference))
            return
        else:
            UniqueTaskMarker(id=task_reference).put()

    defer_kwargs = get_defer_kwargs(kwargs)
    obj_kwargs = strip_defer_kwargs(kwargs)

    # have to pickle the callable within the wrapper because
    # the special treatment that deferred.serialize uses to allow
    # things like instance methods to be pickled doesn't work for
    # the arguments
    pickled_obj = deferred.serialize(obj, *args, **obj_kwargs)

    task = deferred.defer(task_wrapper, pickled_obj, task_reference, **defer_kwargs)

    task_state = TaskState(
        id=task.name,
        task_name=task.name,
        task_reference=task_reference,
        unique=unique,
        queue_name=kwargs.get('_queue', 'default'),
        pickle=pickled_obj
    )

    try:
        task_state.deferred_args = unicode(args)
        task_state.deferred_kwargs = unicode(strip_defer_kwargs(kwargs))
        task_state.deferred_function = get_func_repr(obj)
    except:
        pass
    task_state.put()

    return task_state
