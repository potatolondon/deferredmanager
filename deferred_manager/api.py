import datetime
import json
import pickle
import webapp2

from operator import itemgetter

from google.appengine.api.logservice import logservice
from google.appengine.api import taskqueue
from google.appengine.datastore.datastore_query import Cursor
from google.appengine.ext import ndb

from .models import TaskState, UniqueTaskMarker
from .utils import get_queue_info
from .wrapper import defer


def _serializer(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()

    if hasattr(obj, '__dict__'):
        return obj.__dict__

    raise ValueError(obj)


def dump(obj):
    return json.dumps(obj, default=_serializer)


all_queue_info = get_queue_info()


class QueueListHandler(webapp2.RequestHandler):
    def get(self):
        ctx = {
            "queues": [q for q in all_queue_info.queue]
        }

        self.response.content_type = "application/json"
        self.response.write(dump(ctx))


class QueueHandler(webapp2.RequestHandler):
    def get(self, queue_name):
        cursor = self.request.GET.get('cursor')

        if cursor:
            cursor = Cursor(urlsafe=cursor)

        limit = int(self.request.GET.get('limit', 1000))

        if not limit:
            tasks = []
            new_cursor = more = None
        else:
            tasks, new_cursor, more = (
                TaskState
                .query(TaskState.queue_name == queue_name)
                .order(-TaskState.deferred_at)
                .fetch_page(
                    limit,
                    start_cursor=cursor)
            )

        stats = self.get_queue_stats(queue_name)
        ctx = {}
        ctx['stats'] = {
            k: getattr(stats, k)
            for k in (
                "tasks", "executed_last_minute", "in_flight", "enforced_rate",)
        }
        if stats.oldest_eta_usec:
            ctx['stats']['oldest_eta'] = datetime.datetime.utcfromtimestamp(
                stats.oldest_eta_usec / 1e6)
        ctx['tasks'] = [t.to_dict() for t in tasks]
        if new_cursor:
            ctx['cursor'] = new_cursor.urlsafe()

        self.response.content_type = "application/json"
        self.response.write(dump(ctx))

    def delete(self, queue_name):
        self.get_queue_stats(queue_name).queue.purge()

        @ndb.transactional_tasklet(xg=True)
        def purge_task_states(task_state):
            task_state.is_complete = task_state.is_permanently_failed = True
            task_state.was_purged = True

            task_state_fut = task_state.put_async()

            delete_fut = (
                ndb.Key(UniqueTaskMarker, task_state.task_reference)
                .delete_async()
            )

            yield task_state_fut, delete_fut
            raise ndb.Return(task_state_fut)

        futures = []
        for task_state in (
                TaskState
                .query(
                    TaskState.queue_name == queue_name,
                    TaskState.is_complete == False,
                    TaskState.is_running == False
                )):
            futures.append(purge_task_states(task_state))

        for fut in futures:
            fut.get_result()

        self.response.content_type = "application/json"
        self.response.write(dump({
            "message": "Purging " + queue_name
        }))

    @classmethod
    def get_queue_stats(cls, queue_name):
        return taskqueue.QueueStatistics.fetch(queue_name)


class TaskInfoHandler(webapp2.RequestHandler):
    def get(self, queue_name, task_name):
        task_state = TaskState.get_by_id(task_name)

        if not task_state:
            self.response.set_status(404)
            return

        ctx = {
            'task': task_state.to_dict(),
        }
        if task_state.request_log_ids:
            ctx['logs'] = sorted(
                get_logs(task_state.request_log_ids.split(','), logservice.LOG_LEVEL_INFO),
                key=itemgetter('start_time'),
                reverse=True)

        self.response.content_type = "application/json"
        self.response.write(dump(ctx))

class ReRunTaskHandler(webapp2.RequestHandler):
    def post(self, queue_name, task_name):
        task_state = TaskState.get_by_id(task_name)

        self.response.content_type = "application/json"
        if not task_state:
            self.response.set_status(404)
            return

        if not task_state.is_complete:
            self.response.set_status(400)
            self.response.write(dump({
                "message": "Could not re-run task. Task has not yet finished running"
            }))
            return

        fn, args, kwargs = pickle.loads(task_state.pickle)

        new_task = defer(
            fn,
            unique=task_state.unique,
            task_reference=task_state.task_reference,
            _queue=task_state.queue_name,
            *args,
            **kwargs
        )


        if new_task:
            self.response.write(dump({
                "task_id": new_task.task_name,
                "message": "Re-running task"
            }))
        else:
            self.response.write(dump({
                "message": "Could not re-run task. "
                    "A task with the same reference is already running and the task has been marked as unique."
            }))


class LogHandler(webapp2.RequestHandler):
    def get(self, log_id):
        log_level = int(
            self.request.GET.get('level', logservice.LOG_LEVEL_INFO))
        ctx = {
            'log': next(get_logs([log_id], log_level), None)
        }

        self.response.content_type = "application/json"
        self.response.write(dump(ctx))


def get_logs(log_ids, log_level):
    for request_log in logservice.fetch(minimum_log_level=log_level,
                                        include_incomplete=True,
                                        include_app_logs=True,
                                        request_ids=log_ids):

        d = {name: getattr(request_log, name)
            for name, val in request_log.__class__.__dict__.iteritems()
            if isinstance(val, property) and not name.startswith('_')
        }
        d['start_time'] = datetime.datetime.fromtimestamp(
            request_log.start_time)
        if request_log.end_time:
            d['end_time'] = datetime.datetime.fromtimestamp(
                request_log.end_time)
            d['duration'] = (d['end_time'] - d['start_time']).total_seconds()

        d['app_logs'] = [{
                'time': datetime.datetime.fromtimestamp(app_log.time),
                'level': app_log.level,
                'message': app_log.message
            }
            for app_log in d['app_logs']
            if app_log.level >= log_level
        ]
        yield d
