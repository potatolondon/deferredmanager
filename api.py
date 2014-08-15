import datetime
import json
import webapp2

from google.appengine.ext import db

from .models import TaskState, QueueState

def _serializer(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    raise ValueError

def serialize_model(obj):
    return json.dumps(db.to_dict(obj), default=_serializer)


class QueueListHandler(webapp2.RequestHandler):
    def get(self, queue_name):
        queue_state = QueueState.get_by_key_name(queue_name)

        if not queue_state:
            self.response.set_status(404)
            return

        tasks = TaskState.all().ancestor(queue_state).order("-deferred_at").fetch(limit=1000)

        ctx = {
            'tasks': [task.task_name for task in tasks]
        }

        self.response.content_type = "application/json"
        self.response.write(json.dumps(ctx, default=_serializer))

class TaskInfoHandler(webapp2.RequestHandler):
    def get(self, queue_name, task_name):
        queue_state = QueueState.get_by_key_name(queue_name)
        task_state = TaskState.get_by_key_name(task_name, parent=queue_state)

        if not (queue_state and task_state):
            self.response.set_status(404)
            return

        self.response.content_type = "application/json"
        self.response.write(serialize_model(task_state))


application = webapp2.WSGIApplication([
    ('.+/([\w\d-]+)/([\w\d]+)', TaskInfoHandler),
    ('.+/([\w\d-]+)', QueueListHandler),
])