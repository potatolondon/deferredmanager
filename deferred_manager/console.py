import webapp2
from . import api


class HomeHandler(webapp2.RequestHandler):
    def get(self):
        url = self.request.url
        if not url.endswith("/"):
            url += "/"
        self.redirect(url + 'static/index.html')


application = webapp2.WSGIApplication([
    (r'.+/api/logs/([\w\d-]+)', api.LogHandler),
    (r'.+/api/([\w\d-]+)/([\w\d-]+)/rerun', api.ReRunTaskHandler),
    (r'.+/api/([\w\d-]+)/([\w\d-]+)', api.TaskInfoHandler),
    (r'.+/api/([\w\d-]+)', api.QueueHandler),
    (r'.+/api.*', api.QueueListHandler),
    (r'.*', HomeHandler),
])
