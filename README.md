# GAE Defer Manager (ALPHA)
\- A library to wrap deferring tasks on the Google App Engine Taskqueue API

gae_defer_manager is a wrapper for the deferred library in the Google App Engine SDK to expose the following functionality:

- Task status
- Task ETA
- Allows prevention on duplicate tasks from being added based on an arbitrary reference key


## Setup

Include the gae_defer_manager folder in your project.

Add the following handlers to your app.yaml file (and any other module config files as required):

```yaml
handlers:
  - url: /_ah/queue/deferred
    script: gae_defer_manager.handler.application
    login: admin
    secure: always

  - url: /_ah/deferredapi.*
    script: gae_defer_manager.api.application
    login: admin
    secure: always
```

Change any calls to `google.appengine.ext.deferred.defer` to `gae_defer_manager.defer`

## Usage

Pass arguments to `defer()` in the same way as you would to the GAE defer function.

Optionally, you can pass the following arguments:

- **task_reference**: an arbitrary reference to allow you to identify the task
- **unique_until**: a datetime object. If passed then no other tasks with the same task_reference will be allowed to be deferred until after this datetime.

## Limitations

Adding deferred tasks is limited to one task per second per queue. This is because a datastore entity is saved to persist the task state. It is kept in an entity group to ensure that it returned when the task actually runs.

