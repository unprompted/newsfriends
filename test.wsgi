#!/usr/bin/python

import os
from sqlite3 import dbapi2 as sqlite
import cgi
from openid.consumer import consumer
from openid.store.sqlstore import SQLiteStore
from openid.extensions import pape, sreg
from openid.cryptutil import randomString
import cgitb; cgitb.enable()
from Cookie import SimpleCookie
from genshi.template import TemplateLoader
import cPickle

databaseFilename = '/home/cory/src/idtest/data/db.sqlite'

class Application(object):
	SESSION_COOKIE_NAME = 'sessionId'

	def __init__(self):
		self._store = None
		self._db = None
		self._data = {}
		self._loader = TemplateLoader(os.path.join(os.getcwd(), os.path.dirname(__file__), 'templates'), auto_reload=True)

	def sessionId(self):
		if not self._sessionId:
			sid = None
			if 'HTTP_COOKIE' in self.environment:
				cookieObj = SimpleCookie(self.environment['HTTP_COOKIE'])
				morsel = cookieObj.get(self.SESSION_COOKIE_NAME, None)
				if morsel is not None:
					self._sessionId = morsel.value
			if self._sessionId:
				self.loadSession()
			else:
				self._sessionId = randomString(16, '0123456789ABCDEF')
		return self._sessionId

	def db(self):
		if not self._db:
			self._db = sqlite.connect(databaseFilename)
		return self._db

	def loadSession(self):
		cursor = self.db().cursor()
		cursor.execute('SELECT name, value FROM sessions WHERE session=?', (self.sessionId(),))
		for name, value in cursor:
			self.session[name] = cPickle.loads(str(value))
		cursor.close()

	def saveSession(self):
		cursor = self.db().cursor()
		for name, value in self.session.items():
			blob = sqlite.Binary(cPickle.dumps(value))
			try:
				cursor.execute('INSERT INTO sessions (session, name, value) VALUES (?, ?, ?)', (self.sessionId(), name, blob))
			except Exception, e:
				cursor.execute('UPDATE sessions SET value=? WHERE session=? AND name=?', (blob, self.sessionId(), name))
				if cursor.rowcount == 0:
					raise RuntimeError('Could not save session variable %s=%s: %s' % (name, value, str(e)))
		cursor.execute('DELETE FROM sessions WHERE session=? AND NOT name IN (%s)' % (', '.join('?' for key in self.session)), [self.sessionId()] + self.session.keys())
		self.db().commit()
		cursor.close()

	def store(self):
		if not self._store:
			self._store = SQLiteStore(self.db())
		return self._store

	def consumer(self):
		return consumer.Consumer(self.session, self.store())

	def indexUrl(self, environment):
		return '%s://%s%s%s' % (environment['wsgi.url_scheme'], environment['HTTP_HOST'], (':' + environment['SERVER_PORT']) if environment['SERVER_PORT'] != '80' else '', environment['SCRIPT_NAME'])

	# index
	def handle_(self, environment, startResponse):
		return self.render('index.html')

	def handle_env(self, environment, startResponse):
		return self.render('index.html')

	def handle_verify(self, environment, startResponse):
		form = cgi.FieldStorage(fp=environment['wsgi.input'], environ=environment)
		openidUrl = form.getvalue('openid')
		oid = self.consumer()
		request = oid.begin(openidUrl)
		request.addExtension(pape.Request([pape.AUTH_PHISHING_RESISTANT]))
		request.addExtension(sreg.SRegRequest(required=['nickname'], optional=['fullname', 'email']))
		trustUrl = self.indexUrl(environment)
		returnTo = os.path.join(self.indexUrl(environment), 'process')
		if request.shouldSendRedirect():
			redirectUrl = request.redirectURL(trustUrl, returnTo, immediate=False)
			return self.redirect(redirectUrl)
		else:
			result = request.htmlMarkup(trustUrl, returnTo, form_tag_attrs={'id': 'openid_message'}, immediate=False)
			startResponse('200 OK', [
				('Content-Type', 'text/html'),
				('Content-Length', str(len(result))),
				('Set-Cookie', '%s=%s;' % (self.SESSION_COOKIE_NAME, self.sessionId()))
			])
			self.saveSession()
			return [result]

	def handle_process(self, environment, startResponse):
		form = cgi.FieldStorage(fp=environment['wsgi.input'], environ=environment)
		fields = {}
		for key in form:
			fields[key] = form.getvalue(key)
		oid = self.consumer()
		trustUrl = self.indexUrl(environment)
		info = oid.complete(fields, os.path.join(trustUrl, 'process'))

		if info.status == consumer.FAILURE and info.getDisplayIdentifier():
			raise RuntimeError('Verification of %s failed: %s' % (cgi.escape(info.getDisplayIdentifier()), info.message))
		elif info.status == consumer.SUCCESS:
			self.session['oid'] = info.getDisplayIdentifier()
			if info.endpoint.canonicalID:
				self.session['oid'] = info.endpoint.canonicalID
			self.session['pape'] = pape.Response.fromSuccessResponse(info)
			self.session['sreg'] = sreg.SRegResponse.fromSuccessResponse(info)
			return self.redirect(self.environment['SCRIPT_NAME'])
		elif info.status == consumer.CANCEL:
			raise RuntimeError('Verification canceled.')
		else:
			raise RuntimeError('Verification failed: ' + info.message)

	def handle_logout(self, environment, startResponse):
		try:
			del self.session['oid']
		except:
			pass
		return self.redirect(self.environment['SCRIPT_NAME'])

	def handleError(self, environment, startResponse):
		return self.render('index.html')

	def redirect(self, url):
		response = ''
		self.startResponse('302 Found', [
			('Location', url),
			('Content-Length', str(len(response))),
			('Set-Cookie', '%s=%s;' % (self.SESSION_COOKIE_NAME, self.sessionId()))
		])
		self.saveSession()
		return [response]

	def render(self, template, response='200 OK'):
		self._data['session'] = self.session
		self._data['environment'] = self.environment
		self.saveSession()
		stream = self._loader.load(template).generate(**self._data)
		result = stream.render('html', doctype='html')
		self.startResponse(response, [
			('Content-Type', 'text/html'),
			('Content-Length', str(len(result))),
			('Set-Cookie', '%s=%s;' % (self.SESSION_COOKIE_NAME, self.sessionId()))
		])
		return [result]

	def handler(self, environment, startResponse):
		self.environment = environment
		self.startResponse = startResponse
		self._sessionId = None
		self._db = None
		self._store = None
		self.session = {}
		self._data = {}
		self.session['id'] = self.sessionId()
		path = environment['PATH_INFO'].lstrip('/')
		try:
			method = getattr(self, 'handle_' + path)
		except:
			raise RuntimeError('Method for %s was not found.' % environment['PATH_INFO'])
		try:
			return method(environment, startResponse)
		except Exception, e:
			self._data['error'] = str(e)
			return self.handleError(environment, startResponse)

app = Application()
application = app.handler

if __name__ == '__main__':
	cursor = app.db().cursor()
	cursor.execute('CREATE TABLE IF NOT EXISTS sessions (session TEXT, name TEXT, value BLOB, UNIQUE (session, name))')
	try:
		app.store().createTables()
	except:
		pass
	app.store().cleanup()
	app.db().commit()
