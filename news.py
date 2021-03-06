#!/usr/bin/python

import os
import MySQLdb as sql
from MySQLdb.connections import IntegrityError
import cgi
from openid.consumer import consumer
from openid.store.sqlstore import MySQLStore
from openid.cryptutil import randomString
from Cookie import SimpleCookie
from genshi.template import TemplateLoader
import pickle
import mimetypes
import simplejson
import urllib
import urllib2
import datetime
import feedparser
import time
import lxml.etree
from lxml.html.clean import Cleaner
import base64
import StringIO
import sys
import hashlib
import urlparse

feedparser.SANITIZE_HTML = False
cleaner = Cleaner(host_whitelist=['www.youtube.com'])

dbArgs = {'user': 'news', 'passwd': 'news', 'db': 'news'}
userAgent = 'UnpromptedNews/1.0'
useRobots = False
realm = 'http://www.unprompted.com/news'

def json(method):
	method.contentType = 'application/json'
	return method

def jsonDefaultHandler(obj):
	if isinstance(obj, time.struct_time):
		return time.mktime(obj)
	elif isinstance(obj, datetime.datetime):
		return time.mktime(obj.timetuple())
	else:
		raise TypeError, 'Object of type %s with value of %s is not JSON serializable' % (type(obj), repr(obj))

def cleanHtml(html):
	result = cleaner.clean_html(html)
	tree = lxml.etree.HTML(result)
	for node in tree.findall('.//a'):
		node.attrib['target'] = '_blank'
	return lxml.etree.tostring(tree, encoding='utf-8')

class FeedCache(object):
	def __init__(self, db):
		self._db = db

	def get(self, url):
		document = None
		cursor = self._db.cursor()
		cursor.execute('SELECT document FROM feeds WHERE url=%s', (url,))
		row = cursor.fetchone()
		if row:
			document = row[0]
		cursor.close()
		return document.encode('utf-8') if document else None

	def fetch(self, url):
		cursor = self._db.cursor()
		try:
			lastAttempt = None
			lastUpdate = None
			error = None
			document = None
			cursor.execute('SELECT lastAttempt, error, lastUpdate, document FROM feeds WHERE url=%s', (url,))
			row = cursor.fetchone()
			if row:
				lastAttempt, error, lastUpdate, document = row
			now = datetime.datetime.now()
			if not lastAttempt or now - lastAttempt > datetime.timedelta(minutes=5):
				lastAttempt = now
				try:
					headers = {'User-Agent': userAgent}
					response = urllib2.urlopen(urllib2.Request(url, None, headers), timeout=15)
					encoding = None
					if 'Content-Type' in response.headers:
						contentType = response.headers['Content-Type']
						if 'charset=' in contentType:
							encoding = contentType.split('charset=')[-1]
					stringData = response.read()

					# If the HTTP response didn't include
					# an encoding, let ElementTree parse
					# the document and give it back in a
					# known encoding.
					if not encoding:
						tree = lxml.etree.fromstring(stringData)
						encoding = 'utf-8'
						stringData = lxml.etree.tostring(tree, encoding=encoding)

					document = unicode(stringData, encoding)
					error = None
					lastUpdate = now
				except Exception, e:
					error = str(e)
			cursor.execute('REPLACE INTO feeds (url, lastAttempt, error, lastUpdate, document) VALUES (%s, %s, %s, %s, %s)', (url, lastAttempt, error, lastUpdate, document))
		finally:
			cursor.close()
			self._db.commit()
		return {'lastAttempt': lastAttempt, 'lastUpdate': lastUpdate}

def generateFeedOutline(parent, subscriptions, parentSubscription=None):
	for subscription in subscriptions:
		if subscription['parent'] == parentSubscription:
			attribs = {'title': subscription['name'], 'text': subscription['name']}
			if subscription['url']:
				attribs['xmlUrl'] = subscription['url']
				attribs['htmlUrl'] = subscription['url']
				subscription['type'] = 'rss'
			outline = lxml.etree.SubElement(parent, 'outline', attribs)
			generateFeedOutline(outline, subscriptions, subscription['id'])

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
			self._db = sql.connect('localhost', charset='utf8', use_unicode=True, **dbArgs)
			self._db.set_character_set('utf8')
			cursor = self._db.cursor()
			cursor.execute('SET NAMES utf8')
			cursor.execute('SET CHARACTER SET utf8')
			cursor.execute('SET character_set_connection=utf8')
			cursor.close()
		return self._db

	def loadSession(self):
		cursor = self.db().cursor()
		cursor.execute('SELECT name, value FROM sessions WHERE session=%s', (self.sessionId(),))
		for name, value in cursor:
			self.session[name] = pickle.loads(base64.b64decode(value))
		cursor.close()

	def saveSession(self):
		cursor = self.db().cursor()
		for name, value in self.session.items():
			blob = base64.b64encode(pickle.dumps(value))
			cursor.execute('REPLACE INTO sessions (session, name, value) VALUES (%s, %s, %s)', (self.sessionId(), name, blob))
		cursor.execute('DELETE FROM sessions WHERE session=%%s AND NOT name IN (%s)' % (', '.join('%s' for key in self.session)), [self.sessionId()] + self.session.keys())
		self.db().commit()
		cursor.close()

	def loginUser(self):
		cursor = self.db().cursor()
		cursor.execute('SELECT user FROM identities WHERE identity=%s', (self.session['oid'],))
		row = cursor.fetchone()
		if row:
			self.session['userId'] = row[0]
			cursor.execute('SELECT secret, username, public FROM users WHERE id=%s', (row[0],))
			secret, username, public = cursor.fetchone()
			self.session['secret'] = secret
			self.session['username'] = username
			self.session['public'] = public
		else:
			self.session['secret'] = randomString(16, '0123456789ABCDEF')
			self.session['username'] = None
			self.session['public'] = False
			cursor.execute('INSERT INTO users (secret) VALUES (%s)', (self.session['secret'],))
			self.session['userId'] = cursor.lastrowid
			cursor.execute('INSERT INTO identities (user, identity) VALUES (%s, %s)', (self.session['userId'], self.session['oid']))
			self.db().commit()
		cursor.close()

	def store(self):
		if not self._store:
			self._store = MySQLStore(self.db())
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
		returnTo = realm + '/process'
		if oidRequest.shouldSendRedirect():
			redirectUrl = oidRequest.redirectURL(realm, returnTo, immediate=False)
			return self.redirect(request, redirectUrl)
		else:
			result = oidRequest.htmlMarkup(realm, returnTo, form_tag_attrs={'id': 'openid_message'}, immediate=False)
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
		info = oid.complete(fields, realm + '/process')

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
		for key in ('oid', 'username', 'secret', 'public'):
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
		cursor.execute('INSERT INTO subscriptions (user, url) VALUES (%s, %s)', (request.session['userId'], feedUrl))
		result['affectedRows'] = cursor.rowcount
		cursor.close()
		request.db().commit()
		return self.json(request, result)

	@json
	def handle_deleteSubscription(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		form = request.form()
		feed = form.getvalue('id')
		if not feed:
			raise RuntimeError('Missing feed id.')
		result = {}
		cursor = request.db().cursor()
		cursor.execute('DELETE FROM subscriptions WHERE user=%s AND id=%s', (request.session['userId'], feed))
		result['affectedRows'] = cursor.rowcount
		cursor.close()
		request.db().commit()
		return self.json(request, result)

	@json
	def handle_updateSubscription(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		form = request.form()
		subscription = form.getvalue('id')
		if not subscription:
			raise RuntimeError('Missing id.')
		keys = form.keys()
		keys.remove('id')
		allowedKeys = ('name', 'url')
		for key in keys:
			if not key in allowedKeys:
				raise RuntimeError('Invalid key: ' + key)
		values = [form.getvalue(key) for key in keys]
		# Clear recommendedUrl if we're updating url, as it was only
		# relevant for the old URL and will be updated when fetching.
		if 'url' in keys:
			keys.append('recommendedUrl')
			values.append(None)
		cursor = request.db().cursor()
		cursor.execute(
			'UPDATE subscriptions SET %s WHERE user=%%s AND id=%%s' % ', '.join('%s=%%s' % (key,) for key in keys),
			values + [request.session['userId'], subscription])
		rows = cursor.rowcount
		cursor.close()
		request.db().commit()
		return self.json(request, {'affectedRows': rows})

	@json
	def handle_getSubscriptions(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		cursor = request.db().cursor()
		cursor.execute('''
			SELECT id, user, name, subscriptions.url AS feedUrl, recommendedUrl, parent, feeds.error, feeds.lastAttempt, feeds.lastUpdate
			FROM subscriptions
			LEFT OUTER JOIN feeds ON feeds.url=subscriptions.url
			WHERE user=%s
			ORDER BY name, subscriptions.url
			''',
			(request.session['userId'],))
		columnNames = [d[0] for d in cursor.description]
		result = {'subscriptions': [dict(zip(columnNames, row)) for row in cursor]}
		for subscription in result['subscriptions']:
			if subscription['feedUrl']:
				cursor.execute('''
					SELECT COUNT(*)
					FROM articles
					LEFT OUTER JOIN statuses ON statuses.feed=articles.feed AND statuses.article=articles.id AND statuses.user=%s
					WHERE articles.feed=%s AND (NOT statuses.isRead OR statuses.isRead IS NULL)
					''',
					(request.session['userId'], subscription['feedUrl'],))
				subscription['unreadCount'] = cursor.fetchone()[0]
			else:
				subscription['unreadCount'] = 0
		result['unread'] = sum(subscription['unreadCount'] for subscription in result['subscriptions'])
		cursor.execute('SELECT COUNT(*) FROM statuses WHERE statuses.user=%s AND statuses.starred', (request.session['userId'],))
		result['starred'] = cursor.fetchone()[0]
		cursor.execute('''
			SELECT COUNT(*)
			FROM articles
			JOIN shares ON shares.user=%s AND shares.feed=articles.feed AND shares.article=articles.id
			LEFT OUTER JOIN statuses ON statuses.user=shares.user AND statuses.feed=articles.feed AND statuses.article=articles.id AND statuses.share=shares.id
			WHERE NOT IFNULL(statuses.isRead, FALSE)
			''',
			(request.session['userId'],))
		result['shared'] = cursor.fetchone()[0]
		cursor.execute('''
			SELECT COUNT(*)
			FROM shares
			JOIN friends ON shares.user=friends.friend AND friends.user=%s
			JOIN articles ON shares.feed=articles.feed AND shares.article=articles.id
			LEFT OUTER JOIN statuses ON statuses.user=%s AND statuses.feed=articles.feed AND statuses.article=articles.id AND statuses.share=shares.id
			WHERE NOT IFNULL(statuses.isRead, FALSE)
			''',
			(request.session['userId'],) * 2)
		result['friends'] = cursor.fetchone()[0]
		cursor.close()
		return self.json(request, result)

	@json
	def handle_getUsers(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		cursor = request.db().cursor()
		cursor.execute('''
			SELECT id, secret, username, public, yourFriends.friend IS NOT NULL AS isFriend, theirFriends.user IS NOT NULL as isTheirFriend
			FROM users
			LEFT OUTER JOIN friends AS yourFriends ON yourFriends.user=%s AND users.id=yourFriends.friend
			LEFT OUTER JOIN friends AS theirFriends ON theirFriends.friend=%s AND users.id=theirFriends.user
			WHERE (public OR yourFriends.friend IS NOT NULL OR theirFriends.user IS NOT NULL) AND id!=%s
			ORDER BY NOT isFriend, username
			''',
			(request.session['userId'],) * 3)
		columnNames = [d[0] for d in cursor.description]
		result = {'users': [dict(zip(columnNames, row)) for row in cursor]}
		for user in result['users']:
			secret = hashlib.sha1(user['secret'] + request.session['secret']).hexdigest()
			user['secret'] = secret
		cursor.close()
		return self.json(request, result)

	@json
	def handle_addFriend(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		form = request.form()
		friendSecret = form.getvalue('secret')
		if not friendSecret:
			raise RuntimeError("Missing secret.")
		cursor = request.db().cursor()
		cursor.execute('SELECT id, secret FROM users ORDER BY username')
		userToAdd = None
		for user, secret in cursor:
			test = hashlib.sha1(secret + request.session['secret']).hexdigest()
			if test == friendSecret:
				userToAdd = user
		if userToAdd:
			cursor.execute('INSERT INTO friends (user, friend) VALUES (%s, %s)', (request.session['userId'], userToAdd))
			rows = cursor.rowcount
		else:
			raise RuntimeError("Could not find friend matching given secret.")
		cursor.close()
		request.db().commit()
		return self.json(request, {'affectedRows': rows});

	@json
	def handle_removeFriend(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		form = request.form()
		friendId = form.getvalue('id')
		if not friendId:
			raise RuntimeError("Missing id.")
		cursor = request.db().cursor()
		cursor.execute('DELETE FROM friends WHERE user=%s AND friend=%s', (request.session['userId'], friendId))
		rows = cursor.rowcount
		cursor.close()
		request.db().commit()
		return self.json(request, {'affectedRows': rows});

	@json
	def handle_fetchFeed(self, request):
		form = request.form()
		feedUrl = form.getvalue('feedUrl')
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
				if detail.value:
					return cleanHtml(detail.value)
				else:
					return u''
			else:
				return cgi.escape(detail.value)

		document = feedCache.get(feedUrl)
		feed = feedparser.parse(StringIO.StringIO(document))
		cursor = request.db().cursor()
		try:
			if 'title_detail' in feed.feed:
				originalFeedTitle = makeHtml(feed.feed.title_detail)
				index = 0
				feedTitle = originalFeedTitle
				if feedTitle:
					while True:
						try:
							cursor.execute('UPDATE subscriptions SET name=%s WHERE url=%s AND name IS NULL', (feedTitle, feedUrl))
							break
						except IntegrityError:
							index += 1
							feedTitle = '%s (%d)' % (originalFeedTitle, index)
			for entry in feed.entries:
				entryTitle = 'No Title'
				entryId = entry.id if 'id' in entry else None
				entryLink = entry.link if 'link' in entry else None
				entryId = entryId or entryLink
				if entryId:
					if len(entryId) > 255:
						entryId = hashlib.md5(entryId).hexdigest()
					if 'title_detail' in entry:
						entryTitle = makeHtml(entry.title_detail)
					if 'content' in entry and entry.content:
						entrySummary = '\n'.join(makeHtml(content) for content in entry.content)
					elif 'summary_detail' in entry:
						entrySummary = makeHtml(entry.summary_detail)
					else:
						entrySummary = ''
					entryPublished = None
					if 'published_parsed' in entry and entry.published_parsed:
						entryPublished = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed))
					elif 'updated_parsed' in entry and entry.updated_parsed:
						entryPublished = datetime.datetime.fromtimestamp(time.mktime(entry.updated_parsed))
					cursor.execute('REPLACE INTO articles (id, feed, title, summary, link, published) VALUES (%s, %s, %s, %s, %s, %s)', (entryId, feedUrl, entryTitle, entrySummary, entryLink, entryPublished))
			if not feed.entries and 'html' in feed.feed and 'links' in feed.feed:
				recommendedUrl = None
				for link in feed.feed.links:
					if link.type == 'application/atom+xml' or link.type == 'application/rss+xml':
						recommendedUrl = urlparse.urljoin(feedUrl, link.href)
						break
				if recommendedUrl:
					cursor.execute('UPDATE subscriptions SET recommendedUrl=%s WHERE url=%s', (recommendedUrl, feedUrl))
		except Exception, e:
			cursor.execute('UPDATE feeds SET error=%s WHERE url=%s', (str(e), feedUrl))
		finally:
			cursor.close()
			request.db().commit()
		return self.json(request, {'feedUrl': feedUrl})

	@json
	def handle_markAllRead(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		cursor = request.db().cursor()
		cursor.execute('''
			REPLACE INTO statuses (feed, article, user, share, isRead, starred)
			SELECT articles.feed, articles.id, %s, -1, TRUE, IFNULL(statuses.starred, FALSE)
			FROM subscriptions, articles
			LEFT OUTER JOIN statuses ON statuses.user=%s AND statuses.feed=articles.feed AND statuses.article=articles.id
			WHERE (subscriptions.user=%s AND subscriptions.url=articles.feed) AND (NOT statuses.isRead OR statuses.isRead IS NULL)
			''',
			[request.session['userId']] * 3)
		rows = cursor.rowcount
		request.db().commit()
		return self.json(request, {'affectedRows': rows})

	@json
	def handle_getNews(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		form = request.form()
		what = form.getvalue('what', 'unread')

		news = {'items': [], 'feeds': form.getlist('feeds[]')}
		times = {}
		feeds = form.getlist('feeds[]')

		cursor = request.db().cursor()
		resultLimit = 100

		if what in ('unread', 'all', 'starred'):
			times['unread'] = -time.time()
			if what == 'unread':
				condition = 'NOT statuses.isRead OR statuses.isRead IS NULL'
			elif what == 'starred':
				condition = 'starred'
			else:
				condition = 'TRUE'
			if len(feeds) > 1:
				feedCondition = 'articles.feed IN (%s)' % (', '.join('%s' for feed in feeds))
			elif len(feeds) == 1:
				feedCondition = 'articles.feed=%s'
			else:
				feedCondition = 'TRUE'
			cursor.execute('''
				SELECT
					articles.id AS id,
					articles.feed AS feed,
					subscriptions.name AS feedName,
					articles.title AS title,
					articles.summary AS summary,
					articles.link AS link,
					articles.published AS published,
					IFNULL(statuses.isRead, FALSE) AS isRead,
					IFNULL(statuses.starred, FALSE) AS starred,
					FALSE AS shared,
					NULL AS share,
					NULL AS sharedBy,
					NULL AS sharedNote
				FROM subscriptions
				JOIN articles ON subscriptions.url=articles.feed
				LEFT OUTER JOIN statuses ON statuses.user=%s AND statuses.feed=articles.feed AND statuses.article=articles.id AND statuses.share=-1
				WHERE (subscriptions.user=%s) AND (__CONDITION__) AND (__FEED_CONDITION__)
				ORDER BY starred DESC, articles.published DESC LIMIT %s
				'''.replace('__CONDITION__', condition).replace('__FEED_CONDITION__', feedCondition),
				[request.session['userId']] * 2 + feeds + [resultLimit + 1])
			times['unread'] += time.time()

			columnNames = [d[0] for d in cursor.description]
			unreadItems = [dict(zip(columnNames, row)) for row in cursor]

			times['sharedByMe'] = -time.time()
			cursor.execute('''
				SELECT
					articles.id AS id,
					articles.feed AS feed,
					subscriptions.name AS feedName,
					articles.title AS title,
					articles.summary AS summary,
					articles.link AS link,
					articles.published AS published,
					IFNULL(statuses.isRead, FALSE) AS isRead,
					IFNULL(statuses.starred, FALSE) AS starred,
					TRUE AS shared,
					shares.id AS share,
					users.username AS sharedBy,
					shares.note AS sharedNote
				FROM articles
				JOIN shares ON shares.user=%s AND shares.feed=articles.feed AND shares.article=articles.id
				LEFT OUTER JOIN subscriptions ON subscriptions.user=%s AND subscriptions.url=articles.feed
				LEFT OUTER JOIN statuses ON statuses.user=%s AND statuses.feed=articles.feed AND statuses.article=articles.id AND statuses.share=shares.id
				LEFT OUTER JOIN users ON users.id=shares.user
				WHERE (__CONDITION__) AND (__FEED_CONDITION__)
				ORDER BY starred DESC, articles.published DESC LIMIT %s
				'''.replace('__CONDITION__', condition).replace('__FEED_CONDITION__', feedCondition),
				[request.session['userId']] * 3 + feeds + [resultLimit + 1])
			times['sharedByMe'] += time.time()
			columnNames = [d[0] for d in cursor.description]
			sharedByMe = [dict(zip(columnNames, row)) for row in cursor]

			times['sharedWithMe'] = -time.time()
			cursor.execute('''
				SELECT
					articles.id AS id,
					articles.feed AS feed,
					subscriptions.name AS feedName,
					articles.title AS title,
					articles.summary AS summary,
					articles.link AS link,
					articles.published AS published,
					IFNULL(statuses.isRead, FALSE) AS isRead,
					IFNULL(statuses.starred, FALSE) AS starred,
					FALSE AS shared,
					shares.id AS share,
					users.username AS sharedBy,
					shares.note AS sharedNote
				FROM articles
				JOIN shares ON shares.feed=articles.feed AND shares.article=articles.id
				JOIN friends ON friends.user=%s AND friends.friend=shares.user
				JOIN users ON users.id=shares.user
				JOIN subscriptions ON subscriptions.url=shares.feed AND subscriptions.user=friends.friend
				LEFT OUTER JOIN statuses ON statuses.user=%s AND statuses.feed=articles.feed AND statuses.article=articles.id AND statuses.share=shares.id
				WHERE (__CONDITION__) AND (__FEED_CONDITION__)
				ORDER BY starred DESC, articles.published DESC LIMIT %s
				'''.replace('__CONDITION__', condition).replace('__FEED_CONDITION__', feedCondition),
				[request.session['userId']] * 2 + feeds + [resultLimit + 1])
			columnNames = [d[0] for d in cursor.description]
			sharedWithMe = [dict(zip(columnNames, row)) for row in cursor]
			times['sharedWithMe'] += time.time()

			# Sort items so that starred items come first and then
			# everything is sorted by date after that.
			def mergeNews(left, right):
				allItems = []
				while left and right:
					if left[0]['starred'] != right[0]['starred']:
						if left[0]['starred']:
							allItems.append(left.pop(0))
						else:
							allItems.append(right.pop(0))
					elif left[0]['published'] >= right[0]['published']:
						allItems.append(left.pop(0))
					else:
						allItems.append(right.pop(0))
				allItems += left
				allItems += right
				return allItems
			allItems = mergeNews(mergeNews(unreadItems, sharedByMe), sharedWithMe)
		elif what == 'shared':
			times['shared'] = -time.time()
			cursor.execute('''
				SELECT
					articles.id AS id,
					articles.feed AS feed,
					subscriptions.name AS feedName,
					articles.title AS title,
					articles.summary AS summary,
					articles.link AS link,
					articles.published AS published,
					IFNULL(statuses.isRead, FALSE) AS isRead,
					IFNULL(statuses.starred, FALSE) AS starred,
					TRUE AS shared,
					shares.id AS share,
					users.username AS sharedBy,
					shares.note AS sharedNote
				FROM articles
				JOIN shares ON shares.user=%s AND shares.feed=articles.feed AND shares.article=articles.id
				LEFT OUTER JOIN subscriptions ON subscriptions.url=articles.feed AND subscriptions.user=%s
				JOIN users ON users.id=%s
				LEFT OUTER JOIN statuses ON statuses.user=%s AND statuses.feed=articles.feed AND statuses.article=articles.id AND statuses.share=shares.id
				ORDER BY starred DESC, articles.published DESC LIMIT %s
				''', [request.session['userId']] * 4 + [resultLimit + 1])
			columnNames = [d[0] for d in cursor.description]
			allItems = [dict(zip(columnNames, row)) for row in cursor]
			times['shared'] += time.time()
		elif what == 'friends':
			times['friends'] = -time.time()
			cursor.execute('''
				SELECT
					articles.id AS id,
					articles.feed AS feed,
					subscriptions.name AS feedName,
					articles.title AS title,
					articles.summary AS summary,
					articles.link AS link,
					articles.published AS published,
					IFNULL(statuses.isRead, FALSE) AS isRead,
					IFNULL(statuses.starred, FALSE) AS starred,
					myShares.id IS NOT NULL AS shared,
					shares.id AS share,
					users.username AS sharedBy,
					shares.note AS sharedNote
				FROM users
				JOIN friends ON users.id=friends.friend AND friends.user=%s
				JOIN subscriptions ON subscriptions.user=users.id
				JOIN shares ON shares.user=friends.friend AND shares.feed=subscriptions.url
				JOIN articles ON shares.feed=articles.feed AND shares.article=articles.id
				LEFT OUTER JOIN shares AS myShares ON myShares.user=%s AND myShares.feed=subscriptions.url AND myShares.article=articles.id
				LEFT OUTER JOIN statuses ON statuses.user=%s AND statuses.feed=articles.feed AND statuses.article=articles.id AND statuses.share=shares.id
				ORDER BY starred DESC, articles.published DESC LIMIT %s
				''', [request.session['userId']] * 3 + [resultLimit + 1])
			columnNames = [d[0] for d in cursor.description]
			allItems = [dict(zip(columnNames, row)) for row in cursor]
			times['friends'] += time.time()
		else:
			raise RuntimeError("Can't list '%s' items." % (what,))

		news['items'] = allItems[:resultLimit]
		for newsItem in news['items']:
			if 'share' in newsItem and newsItem['share']:
				newsItem['comments'] = self.getComments(cursor, newsItem['share'])
		news['more'] = len(allItems) > resultLimit
		news['times'] = times

		cursor.execute('UPDATE users SET lastRefresh=NOW() WHERE id=%s', (request.session['userId'],))
		cursor.close()
		request.db().commit()
		return self.json(request, news)

	def getComments(self, cursor, share):
		cursor.execute('SELECT users.username, comments.comment, comments.time FROM comments, users WHERE comments.share=%s AND comments.user=users.id ORDER by comments.time', (share,))
		columnNames = [d[0] for d in cursor.description]
		return [dict(zip(columnNames, row)) for row in cursor]

	@json
	def handle_addComment(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		form = request.form()
		shareId = form.getvalue('share')
		if not shareId:
			raise RuntimeError('Missing share.')
		comment = form.getvalue('comment')
		if not comment:
			raise RuntimeError('Missing comment.')
		cursor = request.db().cursor()
		cursor.execute('INSERT INTO comments (user, share, comment, time) VALUES (%s, %s, %s, %s)', (request.session['userId'], shareId, comment, datetime.datetime.now()))
		rows = cursor.rowcount
		cursor.execute('SELECT user, article, feed FROM shares WHERE id=%s', (shareId,))
		row = cursor.fetchone()
		if row:
			user, article, feed = row
		else:
			user, article, feed = None, None, None
		cursor.execute('UPDATE statuses SET isRead=FALSE WHERE (share=%s OR share=-1 AND user=%s AND article=%s AND feed=%s) AND isRead=TRUE', (shareId, user, article, feed))
		cursor.close()
		request.db().commit()
		return self.json(request, {'affectedRows': rows})

	@json
	def handle_setStatus(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		form = request.form()
		articleId = form.getvalue('article')
		feedUrl = form.getvalue('feed', '')
		shareId = form.getvalue('share') or -1
		cursor = request.db().cursor()
		cursor.execute('SELECT isRead, starred FROM statuses WHERE feed=%s AND article=%s AND share=%s AND user=%s', (feedUrl, articleId, shareId, request.session['userId']))
		read = False
		starred = False
		row = cursor.fetchone()
		if row:
			read, starred = row
		if 'isRead' in form:
			read = form.getvalue('isRead') == 'true'
		if 'starred' in form:
			starred = form.getvalue('starred') == 'true'
		read = bool(read)
		starred = bool(starred)
		cursor.execute('REPLACE INTO statuses (feed, article, share, user, isRead, starred) VALUES (%s, %s, %s, %s, %s, %s)', (feedUrl, articleId, shareId or -1, request.session['userId'], read, starred))
		cursor.close()
		request.db().commit()
		return self.json(request, {'isRead': read, 'starred': starred})

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
		note = form.getvalue('note', '')
		if share:
			cursor.execute('INSERT INTO shares (article, feed, user, note) VALUES (%s, %s, %s, %s)', (articleId, feedUrl, request.session['userId'], note))
		else:
			cursor.execute('DELETE FROM shares WHERE article=%s AND user=%s', (articleId, request.session['userId']))
		rows = cursor.rowcount
		cursor.close()
		request.db().commit()
		return self.json(request, {'shared': share})

	@json
	def handle_setPreferences(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		form = request.form()
		username = form.getvalue('username')
		public = form.getvalue('public')
		if not username or not public:
			raise RuntimeError('Missing preference(s).')
		public = (public == 'true')
		cursor = request.db().cursor()
		cursor.execute('UPDATE users SET username=%s, public=%s WHERE id=%s', (username, public, request.session['userId']))
		request.session['username'] = username
		request.session['public'] = public
		rows = cursor.rowcount
		cursor.close()
		request.saveSession()
		request.db().commit()
		return self.json(request, {'affectedRows': rows})

	def handle_loadOpml(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		user = request.session['userId']

		cursor = request.db().cursor()

		def importNode(node, parent=None):
			if node.tag == 'outline':
				name = node.attrib['title'].encode('utf-8') if 'title' in node.attrib else None
				url = node.attrib['xmlUrl'].encode('utf-8') if 'xmlUrl' in node.attrib else None
				cursor.execute('REPLACE INTO subscriptions (user, name, url, parent) VALUES (%s, %s, %s, %s)', (user, name, url, parent))
				myId = cursor.lastrowid

				for child in node.getchildren():
					importNode(child, myId)

		form = request.form()
		opml = form['file'].file
		tree = lxml.etree.parse(opml)
		body = tree.getroot().find('body')
		for node in body.getchildren():
			importNode(node)
		cursor.close()
		request.db().commit()
		return self.redirect(request, request.environment['SCRIPT_NAME'])

	def handle_saveOpml(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')

		cursor = request.db().cursor()
		cursor.execute('SELECT id, name, url, parent FROM subscriptions WHERE user=%s', (request.session['userId'],))
		columnNames = [d[0] for d in cursor.description]
		subscriptions = [dict(zip(columnNames, row)) for row in cursor]
		ids = [subscription['id'] for subscription in subscriptions]
		for subscription in subscriptions:
			if not subscription['parent'] in ids:
				subscription['parent'] = None
		cursor.close()
		root = lxml.etree.Element('opml', {'version': '1.0'})
		head = lxml.etree.SubElement(root, 'head')
		title = lxml.etree.SubElement(head, 'title')
		title.text = 'News Friends Subscriptions for ' + (request.session['username'] or 'Anonymous')
		body = lxml.etree.SubElement(root, 'body')
		generateFeedOutline(body, subscriptions)
		result = lxml.etree.tostring(root, encoding='utf-8')
		request.startResponse('200 OK', [
			('Content-Type', 'application/xml; charset=utf-8'),
			('Content-Length', str(len(result))),
		])
		return [result]

	def handle_share(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		form = request.form()
		url = form.getvalue('url')
		title = form.getvalue('title')
		try:
			headers = {'User-Agent': userAgent}
			response = urllib2.urlopen(urllib2.Request(url, None, headers), timeout=15)
			encoding = None
			if 'Content-Type' in response.headers:
				contentType = response.headers['Content-Type']
				if 'charset=' in contentType:
					encoding = contentType.split('charset=')[-1]
			stringData = response.read()

			# If the HTTP response didn't include
			# an encoding, let ElementTree parse
			# the document and give it back in a
			# known encoding.
			if not encoding:
				tree = lxml.etree.fromstring(stringData)
				encoding = 'utf-8'
				stringData = lxml.etree.tostring(tree, encoding=encoding)

			content = unicode(stringData, encoding)
			content = cleanHtml(content)
		except Exception, e:
			content = str(e)
		request.data['url'] = url
		request.data['title'] = title
		request.data['content'] = content
		return self.render(request, 'share.html')

	def handle_postShare(self, request):
		if not 'userId' in request.session:
			raise RuntimeError('Must be logged in.')
		form = request.form()
		url = form.getvalue('url')
		title = form.getvalue('title')
		content = form.getvalue('content')
		content = cleanHtml(content)
		note = form.getvalue('note')
		cursor = request.db().cursor()
		cursor.execute('INSERT INTO articles (id, feed, title, summary, link, published) VALUES (%s, %s, %s, %s, %s, %s)',
			(url, '', title, content, url, datetime.datetime.now()))
		cursor.execute('INSERT INTO shares (article, feed, user, note) VALUES (%s, %s, %s, %s)',
			(url, '', request.session['userId'], note))
		cursor.close()
		request.db().commit()
		request.data['shared'] = True
		return self.render(request, 'share.html')

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
		request.data['baseUrl'] = realm
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
	if 'fetch' in sys.argv:
		lastRefresh = datetime.datetime.now()
		while True:
			try:
				def startResponse(result, headers):
					pass
				request = Request({}, startResponse)

				cursor = request.db().cursor()
				cursor.execute('SELECT MAX(lastRefresh) FROM users')
				row = cursor.fetchone()
				active = not lastRefresh or row and row[0] > lastRefresh
				cursor.close()

				lastRefresh = datetime.datetime.now()

				while True:
					cursor = request.db().cursor()
					cursor.execute('SELECT DISTINCT subscriptions.url FROM subscriptions LEFT OUTER JOIN feeds ON subscriptions.url=feeds.url WHERE subscriptions.url IS NOT NULL AND feeds.lastAttempt IS NULL')
					urls = [row[0] for row in cursor]
					reason = 'noLastAttempt'

					if not urls:
						cursor.execute('SELECT DISTINCT subscriptions.url FROM subscriptions LEFT OUTER JOIN feeds ON subscriptions.url=feeds.url WHERE subscriptions.url IS NOT NULL ORDER BY feeds.lastAttempt LIMIT 1')
						urls = [row[0] for row in cursor]
						reason = ['inactive', 'active'][active]
					cursor.close()

					for url in urls:
						if url:
							request = Request({'QUERY_STRING': 'feedUrl=' + urllib.quote(url), 'wsgi.input': ''}, startResponse)
							print reason, app.handle_fetchFeed(request)

					if not active or datetime.datetime.now() - lastRefresh > datetime.timedelta(minutes=5):
						break

				if not active:
					time.sleep(15)
			except KeyboardInterrupt:
				print 'Terminated.'
				break
			except Exception, e:
				import traceback
				traceback.print_exc()
				time.sleep(60)
	else:
		request = Request({}, None)
		cursor = request.db().cursor()
		cursor.execute('CREATE TABLE IF NOT EXISTS sessions (session VARCHAR(16), name VARCHAR(255), value BLOB, UNIQUE (session, name))')
		cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTO_INCREMENT, secret TEXT, username TEXT, lastRefresh TIMESTAMP, public BOOLEAN DEFAULT FALSE)')
		cursor.execute('CREATE TABLE IF NOT EXISTS identities (user INTEGER, identity VARCHAR(255), UNIQUE(user, identity))')
		cursor.execute('CREATE TABLE IF NOT EXISTS subscriptions (id INTEGER PRIMARY KEY AUTO_INCREMENT, user INTEGER, name VARCHAR(255), url VARCHAR(255), recommendedUrl VARCHAR(255), parent INTEGER, UNIQUE(user, url), UNIQUE(user, name))')
		cursor.execute('CREATE TABLE IF NOT EXISTS feeds (url VARCHAR(255) PRIMARY KEY, lastAttempt TIMESTAMP, error TEXT, document MEDIUMTEXT, lastUpdate TIMESTAMP)')
		cursor.execute('CREATE TABLE IF NOT EXISTS articles (id VARCHAR(255), feed VARCHAR(255), title TEXT, summary TEXT, link TEXT, published TIMESTAMP, UNIQUE(id, feed))')
		cursor.execute('CREATE TABLE IF NOT EXISTS statuses (feed VARCHAR(255), article VARCHAR(255), user INTEGER, share INTEGER, isRead BOOLEAN, starred BOOLEAN, UNIQUE(feed, article, user, share))')
		cursor.execute('CREATE TABLE IF NOT EXISTS shares (id INTEGER PRIMARY KEY AUTO_INCREMENT, article VARCHAR(255), feed VARCHAR(255), user INTEGER, note TEXT, UNIQUE(article, feed, user))')
		cursor.execute('CREATE TABLE IF NOT EXISTS friends (user INTEGER, friend INTEGER, UNIQUE(user, friend))')
		cursor.execute('CREATE TABLE IF NOT EXISTS comments (user INTEGER, share INTEGER, comment TEXT, time TIMESTAMP)') 
		try:
			request.store().createTables()
		except:
			pass
		request.store().cleanup()
		request.db().commit()
