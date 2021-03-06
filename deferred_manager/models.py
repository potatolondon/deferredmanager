import datetime

from google.appengine.ext import ndb


class TaskState(ndb.Model):
    task_name = ndb.StringProperty()
    task_reference = ndb.StringProperty(required=False)
    queue_name = ndb.StringProperty(required=True)

    unique = ndb.BooleanProperty(default=False)
    is_complete = ndb.BooleanProperty(default=False)
    is_running = ndb.BooleanProperty(default=False)
    is_permanently_failed = ndb.BooleanProperty(default=False)
    was_purged = ndb.BooleanProperty(default=False)
    first_run = ndb.DateTimeProperty(required=False, default=None)
    retry_count = ndb.IntegerProperty(default=0)
    deferred_function = ndb.TextProperty()
    deferred_args = ndb.TextProperty()
    deferred_kwargs = ndb.TextProperty()
    deferred_at = ndb.DateTimeProperty(auto_now_add=True)
    pickle = ndb.BlobProperty()

    request_log_ids = ndb.TextProperty()

    @property
    def age(self):
        if self.first_run is not None:
            return (datetime.datetime.utcnow() - self.first_run).total_seconds()

    def to_dict(self):
        data = super(TaskState, self).to_dict()
        del data['pickle']
        data['key'] = self.key.id()
        return data

class UniqueTaskMarker(ndb.Model):
    deferred_at = ndb.DateTimeProperty(auto_now_add=True)
