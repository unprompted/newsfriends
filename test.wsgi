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

databaseFilename = '/home/cory/src/idtest/data/db.sqlite'

class Application(object):
	SESSION_COOKIE_NAME = 'sessionId'

	def __init__(self):
		self._store = None
		self._db = None

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
		cursor.execute('SELECT name, value FROM sessions WHERE id=?', (self.sessionId(),))
		for name, value in cursor:
			self.session[name] = value
		cursor.close()

	def saveSession(self):
		cursor = self.db().cursor()
		for name, value in self.session.items():
			try:
				cursor.execute('INSERT INTO sessions (id, name, value) VALUES (?, ?, ?)', (self.sessionId(), name, value))
			except:
				cursor.execute('UPDATE sessions SET value=? WHERE id=? AND name=?', (value, self.sessionId(), name))
		cursor.close()
		self.db().commit()

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
		result = '''
		<html><body><form method="POST" action="%s"><input name="openid" type="text" value="https://www.google.com/accounts/o8/id"></input><input type="submit"></input></form><div>session=%s</div></body></html>
		''' % (os.path.join(self.indexUrl(environment), 'verify'), self.sessionId())
		startResponse('200 OK', [
			('Content-Type', 'text/html'),
			('Content-Length', str(len(result))),
			('Set-Cookie', '%s=%s;' % (self.SESSION_COOKIE_NAME, self.sessionId()))
		])
		return [result]

	def handle_env(self, environment, startResponse):
		result = str(environment)
		startResponse('404 File not found', [
			('Content-Type', 'text/plain'),
			('Content-Length', str(len(result))),
			('Set-Cookie', '%s=%s;' % (self.SESSION_COOKIE_NAME, self.sessionId()))
		])
		return [result]

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
			response = ''
			startResponse('302 Found', [
				('Location', redirectUrl),
				('Content-Length', str(len(response))),
				('Set-Cookie', '%s=%s;' % (self.SESSION_COOKIE_NAME, self.sessionId()))
			])
			return [response]
		else:
			response = request.htmlMarkup(trustUrl, returnTo, form_tag_attrs={'id': 'openid_message'}, immediate=False)
			startResponse('200 OK', [
				('Content-Length', str(len(response))),
				('Set-Cookie', '%s=%s;' % (self.SESSION_COOKIE_NAME, self.sessionId()))
			])
			return [response]

	def handle_process(self, environment, startResponse):
		form = cgi.FieldStorage(fp=environment['wsgi.input'], environ=environment)
		fields = {}
		for key in form:
			fields[key] = form.getvalue(key)
		oid = self.consumer()
		trustUrl = self.indexUrl(environment)
		info = oid.complete(fields, os.path.join(trustUrl, 'process'))

		result = str(info)

		if info.status == consumer.FAILURE and info.getDisplayIdentifier():
			result += '\nVerification of %s failed: %s' % (cgi.escape(info.getDisplayIdentifier()), info.message)
		elif info.status == consumer.SUCCESS:
			result += '\nWelcome, %s.' % (cgi.escape(info.getDisplayIdentifier()),)
			self.session['oid'] = info.getDisplayIdentifier()
			if info.endpoint.canonicalID:
				message += '\nCanonical: %s' % (cgi.escape(info.endpoint.canonicalID),)
				self.session['oid'] = info.endpoint.canonicalID
			papeInfo = pape.Response.fromSuccessResponse(info)
			result += '\n' + str(papeInfo)
			sregInfo = sreg.SRegResponse.fromSuccessResponse(info)
			result += '\n' + str(sregInfo)
		elif info.status == consumer.CANCEL:
			result = 'Verification canceled.'
		else:
			result = 'Verficiation failed:', info.message

		startResponse('200 OK', [
			('Content-Type', 'text/plain'),
			('Content-Length', str(len(result))),
			('Set-Cookie', '%s=%s;' % (self.SESSION_COOKIE_NAME, self.sessionId()))
		])
		return [result]

	def handle404(self, environment, startResponse):
		form = cgi.FieldStorage(fp=environment['wsgi.input'], environ=environment)
		result = 'Method for %s was not found.' % environment['PATH_INFO']
		startResponse('404 File not found', [
			('Content-Type', 'text/plain'),
			('Content-Length', str(len(result))),
		])
		return [result]

	def saveSessionWhenDone(self, result):
		for r in result:
			yield r
		self.saveSession()

	def handler(self, environment, startResponse):
		self.environment = environment
		self.startResponse = startResponse
		self._sessionId = None
		self._db = None
		self.session = {}
		self.session['id'] = self.sessionId()
		path = environment['PATH_INFO'].lstrip('/')
		try:
			method = getattr(self, 'handle_' + path)
		except:
			method = self.handle404
		return self.saveSessionWhenDone(method(environment, startResponse))

app = Application()
application = app.handler

if __name__ == '__main__':
	cursor = app.db().cursor()
	cursor.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, name TEXT, value TEXT, UNIQUE (id, name))')
	try:
		app.store().createTables()
	except:
		pass
	app.store().cleanup()
	app.db().commit()
