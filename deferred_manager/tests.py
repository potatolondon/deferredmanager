# -*- coding: utf8 -*-

import datetime
import os
import unittest
import webapp2

from google.appengine.ext import testbed, deferred
from google.appengine.datastore import datastore_stub_util

TESTCONFIG_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "testconfig")

# this needs setting before importing the wrapper
os.environ['DEFERRED_MANAGER_ROOT_DIR'] = TESTCONFIG_DIR

from .handler import task_wrapper
from .models import TaskState
from .utils import strip_defer_kwargs
from .wrapper import defer


def noop(*args, **kwargs):
    pass


def noop_fail(*args, **kwargs):
    raise Exception


def noop_permanent_fail(*args, **kwargs):
    raise deferred.PermanentTaskFailure


class Foo(object):
    def bar(self):
        pass

    def __call__(self):
        pass


application = webapp2.WSGIApplication([(".*", deferred.TaskHandler)])


class BaseTest(unittest.TestCase):
    def setUp(self):
        self.testbed = testbed.Testbed()

        self.testbed.activate()

        policy = datastore_stub_util.PseudoRandomHRConsistencyPolicy(probability=0)
        self.testbed.init_datastore_v3_stub(consistency_policy=policy)
        self.testbed.init_memcache_stub()
        self.testbed.init_taskqueue_stub(root_path=TESTCONFIG_DIR)
        self.taskqueue_stub = self.testbed.get_stub(
            testbed.TASKQUEUE_SERVICE_NAME)

        super(BaseTest, self).setUp()

    @staticmethod
    def reload(obj):
        return obj.key.get(use_cache=False)


class DeferTaskTests(BaseTest):
    def test_unique_task_ref(self):
        self.assertRaises(
            AssertionError, defer, noop, unique=True)
        self.assertTrue(
            defer(noop, task_reference="project1", unique=True))
        self.assertFalse(
            defer(noop, task_reference="project1", unique=True))

    def test_not_unique_task_ref(self):
        self.assertTrue(
            defer(noop, unique=False))
        self.assertTrue(
            defer(noop, task_reference="project1", unique=False))
        self.assertTrue(
            defer(noop, task_reference="project1", unique=False))

    def test_args_repr(self):
        task_state = defer(noop, 2, u"bår", task_reference="project1")
        self.assertEqual(task_state.deferred_args, u"(2, u'b\\xe5r')")

    def test_kwargs_repr(self):
        task_state = defer(noop, foo="bår", _bar="foo", task_reference="project1")
        self.assertEqual(task_state.deferred_kwargs, u"{'foo': 'b\\xc3\\xa5r'}")

    def test_class_method_repr(self):
        os.environ['test'] = '1'
        task_state = defer(Foo().bar, task_reference="project1")
        self.assertEqual(
            task_state.deferred_function,
            u"<class 'deferred_manager.tests.Foo'>.bar")
        del os.environ['test']

    def test_module_func_repr(self):
        task_state = defer(noop, task_reference="project1")
        self.assertEqual(
            task_state.deferred_function, u"deferred_manager.tests.noop")

    def test_builtin_func_repr(self):
        task_state = defer(map, task_reference="project1")
        self.assertEqual(task_state.deferred_function, u"map")

    def test_callable_obj_func_repr(self):
        task_state = defer(Foo, task_reference="project1")
        self.assertEqual(
            task_state.deferred_function, u"deferred_manager.tests.Foo")

    def test_builtin_method_repr(self):
        task_state = defer(
            datetime.datetime.utcnow, task_reference="project1")
        self.assertEqual(
            task_state.deferred_function, u"<type 'datetime.datetime'>.utcnow")


class HandlerTests(BaseTest):
    @staticmethod
    def make_request(
            queue_name,
            **kwargs):
        request_headers = {
            "X-AppEngine-TaskName": 'dummy-task-name',
            "X-AppEngine-QueueName": queue_name,
        }

        request_environ = {
            "REMOTE_ADDR": "0.1.0.2",
            "SERVER_SOFTWARE": "Google App Engine/1.9.X",
        }

        os.environ.update({
            "HTTP_X_APPENGINE_TASKEXECUTIONCOUNT": str(kwargs.pop('retries', 0)),
            "HTTP_X_APPENGINE_TASKNAME": 'dummy-task-name',
            "HTTP_X_APPENGINE_QUEUENAME": queue_name,
        })

        return webapp2.Request.blank(
            '/',
            headers=request_headers,
            environ=request_environ,
            **kwargs)

    @staticmethod
    def create_task(fn, *args, **kwargs):
        task_state = defer(fn, *args, **kwargs)

        task_pickle = deferred.serialize(
            task_wrapper,
            task_state.key.id(),
            deferred.serialize(fn, *args, **strip_defer_kwargs(kwargs)),
            kwargs['task_reference'],
        )
        return task_state, task_pickle

    def test_success(self):
        task_state, noop_pickle = self.create_task(
            noop, task_reference="project1")

        request = self.make_request('default', POST=noop_pickle)

        response = request.get_response(application)

        self.assertEqual(response.status_int, 200)

        task_state = TaskState.get_by_id(task_state.key.id())
        self.assertTrue(task_state.task_name)
        self.assertTrue(task_state.is_complete)
        self.assertFalse(task_state.is_running)
        self.assertFalse(task_state.is_permanently_failed)

    def test_failure(self):
        task_state, noop_pickle = self.create_task(
            noop_fail, task_reference="project1")

        request = self.make_request('default', POST=noop_pickle)

        response = request.get_response(application)

        self.assertEqual(response.status_int, 500)

        task_state = TaskState.get_by_id(task_state.key.id())
        self.assertFalse(task_state.is_complete)
        self.assertFalse(task_state.is_running)
        self.assertFalse(task_state.is_permanently_failed)

    def test_retry_success(self):
        task_state, noop_pickle = self.create_task(
            noop, task_reference="project1")

        request = self.make_request('default', POST=noop_pickle, retries=2)

        response = request.get_response(application)

        self.assertEqual(response.status_int, 200)

        task_state = TaskState.get_by_id(task_state.key.id())
        self.assertEqual(task_state.retry_count, 2)
        self.assertTrue(task_state.is_complete)
        self.assertFalse(task_state.is_running)
        self.assertFalse(task_state.is_permanently_failed)

    def test_retry_max_retries(self):
        task_state, noop_pickle = self.create_task(
            noop_fail, task_reference="project1")

        # give the task an old age.
        # tasks must fail both the retry and age conditions (if specified)
        task_state.first_run = (
            datetime.datetime.utcnow() - datetime.timedelta(days=2)
        )
        task_state.put()

        request = self.make_request('default', POST=noop_pickle, retries=8)
        response = request.get_response(application)

        self.assertEqual(response.status_int, 500)

        task_state = TaskState.get_by_id(task_state.key.id())
        self.assertEqual(task_state.retry_count, 8)
        self.assertTrue(task_state.is_complete)
        self.assertFalse(task_state.is_running)
        self.assertTrue(task_state.is_permanently_failed)

    def test_permanent_failure(self):
        task_state, noop_pickle = self.create_task(
            noop_permanent_fail, task_reference="project1")

        request = self.make_request('default', POST=noop_pickle)
        response = request.get_response(application)

        self.assertEqual(response.status_int, 200)

        task_state = TaskState.get_by_id(task_state.key.id())
        self.assertEqual(task_state.retry_count, 0)
        self.assertTrue(task_state.is_complete)
        self.assertFalse(task_state.is_running)
        self.assertTrue(task_state.is_permanently_failed)

    def test_no_task_state(self):
        task_state, noop_pickle = self.create_task(noop, task_reference="project1")
        task_state.key.delete()

        request = self.make_request('default', POST=noop_pickle)

        response = request.get_response(application)

        self.assertEqual(response.status_int, 200)

