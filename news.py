#!/usr/bin/python

import os
from sqlite3 import dbapi2 as sqlite
import cgi
from openid.consumer import consumer
from openid.store.sqlstore import SQLiteStore
#from openid.extensions import pape, sreg
from openid.cryptutil import randomString
import cgitb; cgitb.enable()
from Cookie import SimpleCookie
from genshi.template import TemplateLoader
import cPickle
import mimetypes

databaseFilename = os.path.join(os.getcwd(), os.path.dirname(__file__), 'data', 'db.sqlite')

class Request(object):
	SESSION_COOKIE_NAME = 'sessionId' 

	def __init__(self, environment, startResponse):
		self.environment = environment
		self.startResponse = startResponse

		self._sessionId = None
		self._db = None
		self._store = None
		self.session = {}
		self.data = {}
		self.session['id'] = self.sessionId()

	def indexUrl(self):
		return '%s://%s%s%s' % (
			self.environment['wsgi.url_scheme'],
			self.environment['HTTP_HOST'],
			(':' + self.environment['SERVER_PORT']) if self.environment['SERVER_PORT'] != '80' else '',
			self.environment['SCRIPT_NAME']
		)

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

	def loginUser(self):
		cursor = self.db().cursor()
		cursor.execute('SELECT user FROM identities WHERE identity=?', (self.session['oid'],))
		row = cursor.fetchone()
		if row:
			cursor.execute('SELECT secret, username FROM users WHERE id=?', (row[0],))
			secret, username = cursor.fetchone()
			self.session['secret'] = secret
			self.session['username'] = username
		else:
			self.session['secret'] = randomString(16, '0123456789ABCDEF')
			self.session['username'] = None
			cursor.execute('INSERT INTO users (secret) VALUES (?)', (self.session['secret'],))
			user = cursor.lastrowid
			cursor.execute('INSERT INTO identities (user, identity) VALUES (?, ?)', (user, self.session['oid']))
			self.db().commit()
		cursor.close()

	def store(self):
		if not self._store:
			self._store = SQLiteStore(self.db())
		return self._store

	def consumer(self):
		return consumer.Consumer(self.session, self.store())


class Application(object):
	def __init__(self):
		self._loader = TemplateLoader(os.path.join(os.getcwd(), os.path.dirname(__file__), 'templates'), auto_reload=True)

	# index
	def handle_(self, request):
		return self.render(request, 'index.html')

	def handle_env(self, request):
		return self.render(request, 'index.html')

	def handle_verify(self, request):
		form = cgi.FieldStorage(fp=request.environment['wsgi.input'], environ=request.environment)
		openidUrl = form.getvalue('openid_identifier')
		oid = request.consumer()
		oidRequest = oid.begin(openidUrl)
		#oidRequest.addExtension(pape.Request([pape.AUTH_PHISHING_RESISTANT]))
		#oidRequest.addExtension(sreg.SRegRequest(required=['nickname'], optional=['fullname', 'email']))
		trustUrl = request.indexUrl()
		returnTo = os.path.join(request.indexUrl(), 'process')
		if oidRequest.shouldSendRedirect():
			redirectUrl = oidRequest.redirectURL(trustUrl, returnTo, immediate=False)
			return self.redirect(request, redirectUrl)
		else:
			result = oidRequest.htmlMarkup(trustUrl, returnTo, form_tag_attrs={'id': 'openid_message'}, immediate=False)
			request.startResponse('200 OK', [
				('Content-Type', 'text/html'),
				('Content-Length', str(len(result))),
				('Set-Cookie', '%s=%s;' % (request.SESSION_COOKIE_NAME, request.sessionId()))
			])
			request.saveSession()
			return [result]

	def handle_process(self, request):
		form = cgi.FieldStorage(fp=request.environment['wsgi.input'], environ=request.environment)
		fields = {}
		for key in form:
			fields[key] = form.getvalue(key)
		oid = request.consumer()
		trustUrl = request.indexUrl()
		info = oid.complete(fields, os.path.join(trustUrl, 'process'))

		if info.status == consumer.FAILURE and info.getDisplayIdentifier():
			raise RuntimeError('Verification of %s failed: %s' % (cgi.escape(info.getDisplayIdentifier()), info.message))
		elif info.status == consumer.SUCCESS:
			request.session['oid'] = info.getDisplayIdentifier()
			if info.endpoint.canonicalID:
				request.session['oid'] = info.endpoint.canonicalID
			request.loginUser()
			#request.session['pape'] = pape.Response.fromSuccessResponse(info)
			#request.session['sreg'] = sreg.SRegResponse.fromSuccessResponse(info)
			return self.redirect(request, request.environment['SCRIPT_NAME'])
		elif info.status == consumer.CANCEL:
			raise RuntimeError('Verification canceled.')
		else:
			raise RuntimeError('Verification failed: ' + info.message)

	def handle_logout(self, request):
		for key in ('oid', 'username', 'secret'):
			try:
				del request.session[key]
			except:
				pass
		return self.redirect(request, request.environment['SCRIPT_NAME'])

	def handle_static(self, request):
		here = os.path.abspath(os.path.normpath(os.path.join(os.getcwd(), os.path.dirname(__file__))))

		# remove "/static"
		parts = request.environment['PATH_INFO'].lstrip('/').split('/', 1)
		if parts[0] == 'static':
			parts = parts[1:]
		relativePath = os.path.join(*parts)
		absolutePath = os.path.abspath(os.path.normpath(os.path.join(here, 'htdocs', relativePath)))
		if not absolutePath.startswith(here):
			raise RuntimeError('Path outside of static resources: %s, %s' % (absolutePath, here))

		staticFile = open(absolutePath, 'rb') 
		size = os.stat(absolutePath).st_size

		mimeType, encoding = mimetypes.guess_type(absolutePath)
		if not mimeType:
			mimeType = 'application/binary'

		request.startResponse('200 OK', [
			('Content-Length', str(size)),
			('Content-Type', mimeType),
		])

		blockSize = 4096
		if 'wsgi.file_wrapper' in request.environment:
			return request.environment['wsgi.file_wrapper'](staticFile, blockSize)
		else:
			return iter(lambda: staticFile.read(blockSize), '')

	def handleError(self, request):
		return self.render(request, 'index.html')

	def redirect(self, request, url):
		response = ''
		request.startResponse('302 Found', [
			('Location', url),
			('Content-Length', str(len(response))),
			('Set-Cookie', '%s=%s;' % (request.SESSION_COOKIE_NAME, request.sessionId()))
		])
		request.saveSession()
		return [response]

	def render(self, request, template, response='200 OK'):
		request.data['session'] = request.session
		request.data['environment'] = request.environment
		request.saveSession()
		stream = self._loader.load(template).generate(**request.data)
		result = stream.render('html', doctype='html')
		request.startResponse(response, [
			('Content-Type', 'text/html'),
			('Content-Length', str(len(result))),
			('Set-Cookie', '%s=%s;' % (request.SESSION_COOKIE_NAME, request.sessionId()))
		])
		return [result]

	def handler(self, environment, startResponse):
		request = Request(environment, startResponse)

		action = environment['PATH_INFO'].lstrip('/').split('/', 1)[0]
		try:
			try:
				method = getattr(self, 'handle_' + action)
			except:
				raise RuntimeError('Method for %s was not found.' % environment['PATH_INFO'])
			return method(request)
		except Exception, e:
			import traceback
			request.data['error'] = traceback.format_exc()
			return self.handleError(request)

app = Application()
application = app.handler

if __name__ == '__main__':
	request = Request({}, None)
	cursor = request.db().cursor()
	cursor.execute('CREATE TABLE IF NOT EXISTS sessions (session TEXT, name TEXT, value BLOB, UNIQUE (session, name))')
	cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, secret TEXT, username TEXT)')
	cursor.execute('CREATE TABLE IF NOT EXISTS identities (user INTEGER, identity TEXT, UNIQUE(user, identity))')
	try:
		request.store().createTables()
	except:
		pass
	request.store().cleanup()
	request.db().commit()
