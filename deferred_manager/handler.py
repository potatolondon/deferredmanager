import datetime
import logging
import os
import pickle

from google.appengine.ext import ndb, deferred
from google.appengine.api import queueinfo

from .models import TaskState, UniqueTaskMarker

from .utils import attrgetter, get_func_repr, get_queue_info


class TaskWrapper(object):
    def __init__(self):
        self.all_queue_info = get_queue_info().queue

    def __call__(self, task_state_key, obj, task_reference):
        fn, fn_args, fn_kwargs = pickle.loads(obj)

        task_state = self.get_task_state(task_state_key)

        try:
            fn(*fn_args, **fn_kwargs)

        except deferred.SingularTaskFailure as e:
            if task_state and not self.should_retry(task_state):
                self.complete_task(task_state, permanently_failed=True)
            else:
                logging.debug("Failure executing task, task retry forced")
                raise

        except deferred.PermanentTaskFailure as e:
            logging.exception("Permanent failure attempting to execute task")
            if task_state:
                self.complete_task(task_state, permanently_failed=True)
            raise

        except Exception as e:
            logging.exception(e)

            if task_state and not self.should_retry(task_state):
                self.complete_task(task_state, permanently_failed=True)
                logging.warning(
                    "Task has failed {0} times and is {1}s old. "
                    "It will not be retried."
                    .format(task_state.retry_count, task_state.age))

            raise

        else:
            if task_state:
                self.complete_task(task_state)

        finally:
            if task_state:
                task_state.is_running = False
                task_state.put()

    @staticmethod
    @ndb.transactional
    def get_task_state(task_state_key):
        task_state = TaskState.get_by_id(task_state_key)

        if not task_state:
            raise deferred.SingularTaskFailure(
                "Task with ID {0} has no task state. This shouldn't happen. "
                "Task will retry if queue is set to allow retries.".format(task_state_key)
            )

        if task_state.is_running:
            raise deferred.PermanentTaskFailure(
                "Task with ID {0} is already marked as running. "
                "GAE may have fired the same task more than once. "
                "See https://cloud.google.com/appengine/docs/python/taskqueue/#Python_Task_names".format(
                    task_state)
            )

        if task_state.is_complete:
            raise deferred.PermanentTaskFailure(
                "Task with ID {0} is marked as complete. "
                "GAE may have fired the same task more than once. "
                "See https://cloud.google.com/appengine/docs/python/taskqueue/#Python_Task_names".format(
                    task_state)
            )

        task_state.is_running = True
        task_state.task_name = os.environ['HTTP_X_APPENGINE_TASKNAME']

        task_state.retry_count = int(os.environ['HTTP_X_APPENGINE_TASKEXECUTIONCOUNT'])

        if task_state.request_log_ids is None:
            task_state.request_log_ids = os.environ['REQUEST_LOG_ID']
        else:
            task_state.request_log_ids += "," + os.environ['REQUEST_LOG_ID']

        if task_state.first_run is None:
            task_state.first_run = datetime.datetime.utcnow()

        task_state.put()

        return task_state

    @staticmethod
    @ndb.transactional(xg=True)
    def complete_task(task_state, permanently_failed=False):
        task_state.is_complete = True
        task_state.is_permanently_failed = permanently_failed

        if task_state.unique:
            ndb.Key(UniqueTaskMarker, task_state.task_reference).delete()

    def should_retry(self, task_state):
        retry_limit = self.get_retry_limit()
        age_limit = self.get_age_limit()
        # TODO: handle default retry params and task-specific retry params
        if retry_limit is not None and age_limit is not None:
            return (
                retry_limit > task_state.retry_count or
                age_limit >= task_state.age
            )

        elif retry_limit is not None:
            return retry_limit > task_state.retry_count

        elif age_limit is not None:
            return age_limit >= task_state.age

        return True

    def get_queue_info(self):
        queue_name = os.environ['HTTP_X_APPENGINE_QUEUENAME']
        return next(
            qi for qi in self.all_queue_info if qi.name == queue_name)

    def get_retry_limit(self):
        try:
            limit = attrgetter("retry_parameters.task_retry_limit")(self.get_queue_info())
        except AttributeError:
            limit = None

        if limit is not None:
            return int(limit)

    def get_age_limit(self):
        limit = attrgetter("retry_parameters.task_age_limit")(self.get_queue_info())

        if limit is not None:
            queueinfo.ParseTaskAgeLimit(limit)


task_wrapper = TaskWrapper()
