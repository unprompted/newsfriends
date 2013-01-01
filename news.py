#!/usr/bin/python

import os
from sqlite3 import dbapi2 as sqlite
import cgi
from openid.consumer import consumer
from openid.store.sqlstore import SQLiteStore
from openid.cryptutil import randomString
import cgitb; cgitb.enable()
from Cookie import SimpleCookie
from genshi.template import TemplateLoader
import cPickle
import mimetypes
import simplejson
import urllib2
import datetime
import feedparser
import time
from xml.etree import ElementTree as ET

databaseFilename = os.path.join(os.getcwd(), os.path.dirname(__file__), 'data', 'db.sqlite')

def json(method):
	method.contentType = 'application/json'
	return method

def jsonDefaultHandler(obj):
	if isinstance(obj, time.struct_time):
		return time.mktime(obj)
	else:
		raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj))

class FeedCache(object):
	def __init__(self, db):
		self._db = db

	def get(self, url):
		document = None
		cursor = self._db.cursor()
		cursor.execute('SELECT document FROM feeds WHERE url=?', (url,))
		row = cursor.fetchone()
		if row:
			document = row[0]
		cursor.close()
		return document

	def fetch(self, url):
		cursor = self._db.cursor()
		lastAttempt = None
		lastUpdate = None
		error = None
		document = None
		cursor.execute('SELECT lastAttempt, error, lastUpdate, document FROM feeds WHERE url=?', (url,))
		row = cursor.fetchone()
		if row:
			lastAttempt, error, lastUpdate, document = row
		cursor.close()
		now = datetime.datetime.now()
		if not lastAttempt or now - lastAttempt > datetime.timedelta(minutes=5):
			lastAttempt = now
			try:
				headers = {'User-Agent': 'UnpromptedNews/1.0'}
				document = unicode(urllib2.urlopen(urllib2.Request(url, None, headers)).read(), 'utf-8')
				lastUpdate = now
			except Exception, e:
				error = str(e)
		cursor.execute('INSERT OR REPLACE INTO feeds (url, lastAttempt, error, lastUpdate, document) VALUES (?, ?, ?, ?, ?)', (url, lastAttempt, error, lastUpdate, document))
		cursor.close()
		self._db.commit()
		return {'lastAttempt': lastAttempt, 'lastUpdate': lastUpdate}

class Request(object):
	SESSION_COOKIE_NAME = 'sessionId' 

	def __init__(self, environment, startResponse):
		self.environment = environment
		self.startResponse = startResponse

		self._sessionId = None
		self._db = None
		self._store = None
		self._form = None
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
			self._db = sqlite.connect(databaseFilename, detect_types=sqlite.PARSE_DECLTYPES)
			self._db.row_factory = sqlite.Row
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
			self.session['userId'] = row[0]
			cursor.execute('SELECT secret, username FROM users WHERE id=?', (row[0],))
			secret, username = cursor.fetchone()
			self.session['secret'] = secret
			self.session['username'] = username
		else:
			self.session['secret'] = randomString(16, '0123456789ABCDEF')
			self.session['username'] = None
			cursor.execute('INSERT INTO users (secret) VALUES (?)', (self.session['secret'],))
			self.session['userId'] = cursor.lastrowid
			cursor.execute('INSERT INTO identities (user, identity) VALUES (?, ?)', (self.session['userId'], self.session['oid']))
			self.db().commit()
		cursor.close()

	def store(self):
		if not self._store:
			self._store = SQLiteStore(self.db())
		return self._store

	def consumer(self):
		return consumer.Consumer(self.session, self.store())

	def form(self):
		if not self._form:
			self._form = cgi.FieldStorage(fp=self.environment['wsgi.input'], environ=self.environment)
		return self._form


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

	@json
	def handle_addSubscription(self, request):
		form = request.form()
		feedUrl = form.getvalue('feedUrl')
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		if not feedUrl:
			raise RuntimeError('Missing feed URL.')
		result = {}
		cursor = request.db().cursor()
		cursor.execute('INSERT INTO subscriptions (user, url) VALUES (?, ?)', (request.session['userId'], feedUrl))
		result['affectedRows'] = cursor.rowcount
		cursor.close()
		request.db().commit()
		return self.json(request, result)

	@json
	def handle_deleteSubscription(self, request):
		form = request.form()
		feedUrl = form.getvalue('feedUrl')
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		if not feedUrl:
			raise RuntimeError('Missing feed URL.')
		result = {}
		cursor = request.db().cursor()
		cursor.execute('DELETE FROM subscriptions WHERE user=? AND url=?', (request.session['userId'], feedUrl))
		result['affectedRows'] = cursor.rowcount
		cursor.close()
		request.db().commit()
		return self.json(request, result)

	@json
	def handle_getSubscriptions(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		cursor = request.db().cursor()
		cursor.execute('SELECT id, user, name, url, parent FROM subscriptions WHERE user=? ORDER BY name DESC, url DESC', (request.session['userId'],))
		result = {'subscriptions': []}
		for subscription, user, name, feedUrl, parent in cursor:
			result['subscriptions'].append({'id': subscription, 'user': user, 'name': name, 'feedUrl': feedUrl, 'parent': parent})
		cursor.close()
		return self.json(request, result)

	@json
	def handle_fetchFeed(self, request):
		form = request.form()
		feedUrl = form.getvalue('feedUrl')
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		if not feedUrl:
			raise RuntimeError('Missing feed URL.')
		feedCache = FeedCache(request.db())
		if feedUrl.startswith('http://') or feedUrl.startswith('https://'):
			feedCache.fetch(feedUrl)
		else:
			pass

		def makeHtml(detail):
			if detail.type == 'text/plain':
				return cgi.escape(detail.value)
			elif detail.type == 'text/html' or detail.type == 'application/xhtml+xml':
				return detail.value
			else:
				return cgi.escape(detail.value)

		document = feedCache.get(feedUrl)
		feed = feedparser.parse(document)
		cursor = request.db().cursor()
		for entry in feed.entries:
			entryId = entry.id
			entryLink = entry.link if 'link' in entry else None
			entryTitle = makeHtml(entry.title_detail)
			if 'content' in entry and entry.content:
				entrySummary = '\n'.join(makeHtml(content) for content in entry.content)
			else:
				entrySummary = makeHtml(entry.summary_detail)
			entryPublished = None
			if entry.published_parsed:
				entryPublished = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed))
			cursor.execute('INSERT OR REPLACE INTO articles (id, feed, title, summary, link, published) VALUES (?, ?, ?, ?, ?, ?)', (entryId, feedUrl, entryTitle, entrySummary, entryLink, entryPublished))
		cursor.close()
		return self.json(request, {'feedUrl': feedUrl})

	@json
	def handle_getNews(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		news = {'items': []}
		cursor = request.db().cursor()
		# article feed user note
		cursor.execute('''
			SELECT articles.id, articles.feed, articles.title, articles.summary, articles.link, statuses.read, statuses.starred, shares.article IS NOT NULL AS isShared, users.username, sharedNote
			FROM articles
			LEFT OUTER JOIN statuses ON statuses.user=? AND statuses.article=articles.id
			LEFT OUTER JOIN subscriptions ON subscriptions.user=? AND subscriptions.url=articles.feed
			LEFT OUTER JOIN
				(SELECT shares.article AS sharedArticle, friends.friend AS sharedBy, shares.note as sharedNote FROM shares, friends WHERE shares.user=friends.friend AND friends.user=?)
				ON sharedArticle=articles.id
			LEFT OUTER JOIN shares ON shares.article=articles.id AND shares.user=?
			LEFT OUTER JOIN users ON sharedBy=users.id
			WHERE (NOT statuses.read OR statuses.read IS NULL) AND (statuses.user=? OR subscriptions.user=? OR sharedArticle IS NOT NULL)
			ORDER BY published DESC LIMIT 100''',
			(request.session['userId'],) * 6)

		for articleId, feed, title, summary, link, read, starred, shared, sharedBy, sharedNote in cursor:
			news['items'].append({'id': articleId, 'feed': feed, 'title': title, 'summary': summary, 'link': link, 'read': bool(read), 'starred': bool(starred), 'shared': bool(shared), 'sharedBy': sharedBy, 'sharedNote': sharedNote})
		cursor.close()
		return self.json(request, news)

	@json
	def handle_setStatus(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		form = request.form()
		articleId = form.getvalue('article')
		if not articleId:
			raise RuntimeError('Missing article.')
		cursor = request.db().cursor()
		cursor.execute('SELECT read, starred FROM statuses WHERE article=? AND user=?', (articleId, request.session['userId']))
		read = False
		starred = False
		row = cursor.fetchone()
		if row:
			read, starred = row
		if 'read' in form:
			read = form.getvalue('read') == 'true'
		if 'starred' in form:
			starred = form.getvalue('starred') == 'true'
		read = bool(read)
		starred = bool(starred)
		cursor.execute('INSERT OR REPLACE INTO statuses (article, user, read, starred) VALUES (?, ?, ?, ?)', (articleId, request.session['userId'], read, starred))
		cursor.close()
		request.db().commit()
		return self.json(request, {'read': read, 'starred': starred, 'form': form.getvalue('read')})

	@json
	def handle_setShared(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		form = request.form()
		articleId = form.getvalue('article')
		if not articleId:
			raise RuntimeError('Missing article.')
		feedUrl = form.getvalue('feed')
		cursor = request.db().cursor()
		share = form.getvalue('share') == 'true'
		if share:
			cursor.execute('INSERT INTO shares (article, feed, user, note) VALUES (?, ?, ?, ?)', (articleId, feedUrl, request.session['userId'], None))
		else:
			cursor.execute('DELETE FROM shares WHERE article=? AND user=?', (articleId, request.session['userId']))
		rows = cursor.rowcount
		cursor.close()
		request.db().commit()
		return self.json(request, {'shared': share})

	@json
	def handle_setName(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		form = request.form()
		name = form.getvalue('name')
		cursor = request.db().cursor()
		cursor.execute('UPDATE users SET username=? WHERE id=?', (name, request.session['userId']))
		request.session['username'] = name
		rows = cursor.rowcount
		cursor.close()
		request.db().commit()
		return self.json(request, {'affectedRows': rows})

	def handle_loadOpml(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		user = request.session['userId']

		cursor = request.db().cursor()

		def importNode(node, parent=None):
			if node.tag == 'outline':
				name = node.attrib['title'] if 'title' in node.attrib else None
				url = node.attrib['xmlUrl'] if 'xmlUrl' in node.attrib else None
				cursor.execute('INSERT OR REPLACE INTO subscriptions (user, name, url, parent) VALUES (?, ?, ?, ?)', (user, name, url, parent))
				myId = cursor.lastrowid

				for child in node.getchildren():
					importNode(child, myId)

		form = request.form()
		opml = form['file'].file
		tree = ET.parse(opml)
		body = tree.getroot().find('body')
		for node in body.getchildren():
			importNode(node)
		cursor.close()
		request.db().commit()
		return self.redirect(request, request.environment['SCRIPT_NAME'])

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

	def json(self, request, data):
		request.data['session'] = request.session
		request.data['environment'] = request.environment
		request.saveSession()
		result = simplejson.dumps(data, default=jsonDefaultHandler)
		request.startResponse('200 OK', [
			('Content-Type', 'application/json'),
			('Content-Length', str(len(result))),
		])
		return [result]

	def handler(self, environment, startResponse):
		request = Request(environment, startResponse)

		action = environment['PATH_INFO'].lstrip('/').split('/', 1)[0]
		method = None
		try:
			try:
				method = getattr(self, 'handle_' + action)
			except:
				raise RuntimeError('Method for %s was not found.' % environment['PATH_INFO'])
			return method(request)
		except Exception, e:
			if hasattr(method, 'contentType'):
				contentType = method.contentType
			else:
				contentType = 'text/html'
			if contentType == 'application/json':
				import traceback
				return self.json(request, {'error': str(e), 'traceback': traceback.format_exc()})
			else:
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
	cursor.execute('CREATE TABLE IF NOT EXISTS subscriptions (id INTEGER PRIMARY KEY AUTOINCREMENT, user INTEGER, name TEXT, url TEXT, parent INTEGER, UNIQUE(user, url), UNIQUE(user, name))')
	cursor.execute('CREATE TABLE IF NOT EXISTS feeds (url TEXT PRIMARY KEY, lastAttempt TIMESTAMP, error TEXT, document TEXT, lastUpdate TIMESTAMP)')
	cursor.execute('CREATE TABLE IF NOT EXISTS articles (id TEXT PRIMARY KEY, feed TEXT, title TEXT, summary TEXT, link TEXT, published TIMESTAMP)')
	cursor.execute('CREATE TABLE IF NOT EXISTS statuses (article TEXT, user INTEGER, read BOOLEAN, starred BOOLEAN, UNIQUE(article, user))')
	cursor.execute('CREATE TABLE IF NOT EXISTS shares (id INTEGER PRIMARY KEY AUTOINCREMENT, article TEXT, feed TEXT, user INTEGER, note TEXT, UNIQUE(article, feed, user))')
	cursor.execute('CREATE TABLE IF NOT EXISTS friends (user INTEGER, friend INTEGER, UNIQUE(user, friend))')
	try:
		request.store().createTables()
	except:
		pass
	request.store().cleanup()
	request.db().commit()
