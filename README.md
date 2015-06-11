GAE Defer Manager (ALPHA)
========================

## A library to wrap deferring tasks on the Google App Engine Taskqueue API

gae_defer_manager is a wrapper for the deferred library in the Google App Engine SDK to expose the following functionality:

* Task status
* Task ETA
* Allows prevention on duplicate tasks from being added based on an arbitrary reference key
* Allows tasks to be re-run

## Setup

Change any calls to `google.appengine.ext.deferred.defer` to `deferred_manager.defer`


## Console setup

Add the following handlers to your app.yaml file (and any other module config files as required):

```yaml
handlers:
  - url: /_ah/deferredconsole/static/
    static_dir: deferred_manager/static
    expiration: 1d
  - url: /_ah/deferredconsole.*
    script: deferred_manager.application
    login: admin
    secure: always
```

## Usage

Pass arguments to `defer()` in the same way as you would to the GAE defer function.

Optionally, you can pass the following arguments:

- **task_reference**: an arbitrary reference to allow you to identify the task
- **unique**: Boolean flag. If passed then no other tasks with the same task_reference will be allowed to be deferred until the created task has been run. If there is already a task running that `defer()` will not return a `TaskState` object.

## Task console

The task console can be found at /_ah/deferredconsole/static/index.html
