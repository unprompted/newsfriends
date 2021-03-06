var gSubscriptions = [];
var gSubscriptionsToFetch = [];
var gWorkerCount = 0;
var gSubscriptionsToFetchCount = 0;
var gSubscriptionsFetchedCount = 0;
var gSelected = -1;
var gFocused = -1;
var gCursorIndex = -1;
var gNews = [];
var gNewsToLoad = 'unread';
var gSubscriptionTree = null;
var gSelectedSubscription = null;
var gShowOnlyUnreadSubscriptions = true;

$(document).ready(function() {
	$("#add_subscription").click(addSubscription);
	$("#refresh_feeds").click(loadNews);
	$("#mark_all_read_feeds").click(markAllRead);
	$("#user_apply").click(setPreferences);
	$("#hide_errors").click(hideErrors);

	makeMenu();

	var section = 'news';
	if (document.location.hash) {
		var hash = document.location.hash.substring(1);
		var parts = hash.split('/');
		section = parts[0];
		if (section == "news" && parts.length > 1) {
			gNewsToLoad = parts[1];
		}
	}
	showSection("content_" + section);
});

function selectArticle(index, expand) {
	gCursorIndex = index;
	if (expand) {
		$("#articles").children().eq(gFocused).removeClass('focused');
		$("#articles").children().eq(gSelected).removeClass('selected');
		gSelected = index;
		gFocused = index;
		if (gSelected >= 0 && gSelected < $("#articles").children().length) {
			var toShow = $("#articles").children().eq(gSelected);
			toShow.addClass('selected');
			toShow.trigger('markRead');
			toShow.get(0).scrollIntoView(true);
		}
	} else {
		$("#articles").children().eq(gFocused).removeClass('focused');
		gFocused = index;
		if (gFocused >= 0 && gFocused < $("#articles").children().length) {
			var toShow = $("#articles").children().eq(gFocused);
			toShow.addClass('focused');
			toShow.get(0).scrollIntoView(true);
		}
	}
}

$(document).keypress(function(event) {
	if (event.target.tagName != 'TEXTAREA' && event.target.tagName != 'INPUT' && event.target.tagName != 'SELECT') {
		if ($("#content_news").is(":visible")) {
			var character = String.fromCharCode(event.keyCode);
			var cursor = gCursorIndex;
			var expand = gCursorIndex == gSelected;
			if (character == 'j') {
				expand = true;
				if (cursor == -1) {
					cursor = 0;
				} else if (cursor >= 0 && cursor < $("#articles").children().length - 1) {
					cursor++;
				}
			} else if (character == 'k') {
				expand = true;
				if (cursor == -1) {
					cursor = $("#articles").children().length - 1;
				} else if (cursor > 0 && cursor < $("#articles").children().length) {
					cursor--;
				}
			} else if (character == 'n') {
				expand = false;
				if (cursor == -1) {
					cursor = 0;
				} else if (cursor >= 0 && cursor < $("#articles").children().length - 1) {
					cursor++;
				}
			} else if (character == 'p') {
				expand = false;
				if (cursor == -1) {
					cursor = $("#articles").children().length - 1;
				} else if (cursor > 0 && cursor < $("#articles").children().length) {
					cursor--;
				}
			} else if (character == ' ') {
				expand = !expand;
				if (!expand) {
					$("#articles").children().eq(gSelected).removeClass('selected');
					gSelected = -1;
				}
			} else if (character == 'r') {
				loadNews();
			} else if (character == 's') {
				if (gCursorIndex != -1) {
					$("#articles").children().eq(gCursorIndex).trigger('toggleStarred');
				}
			}

			selectArticle(cursor, expand);
		}
	}
});

function makeMenu() {
	$(".content").each(function() {
		var div = document.createElement('div');
		$(div).addClass("menu");
		$(div).text($(this).data("name"));
		var id = $(this).attr("id");
		$(div).click(function() {
			showSection(id);
		});
		$(div).attr("id", "menu_" + id);
		$("#menu").append(div);

		if (id == "content_news") {
			var subMenu = document.createElement('div');
			[
				{text: "Unread Items", name: "unread"},
				{text: "All Items", name: "all"},
				{text: "Shared Items", name: "shared"},
				{text: "Items from Friends", name: "friends"},
				{text: "Starred Items", name: "starred"},
			].forEach(function(details) {
				var item = document.createElement('div');
				$(item).text(details.text);
				$(item).attr('id', 'submenu_news_' + details.name);
				$(item).click(function() { newsSubMenu(details.name); });
				$(item).addClass("subMenu");
				var count = document.createElement('span');
				$(count).addClass('count');
				$(count).attr('id', 'count_' + details.name);
				$(item).append(count);
				$(subMenu).append(item);
			});
			$("#menu").append(subMenu);
		}
	});
	gSubscriptionTree = $(document.createElement('div'));
	$("#menu").append(gSubscriptionTree);
	$(gSubscriptionTree).addClass("subscriptionTree");
}

function showSectionNoLoad(id) {
	$(".menu").removeClass("selected");
	$(".content").hide();
	$('#' + id).show();
	$('#menu_' + id).addClass("selected");

	if (id != 'content_news') {
		$(".subMenu").removeClass("selected");
	}

	var subSection = id == 'content_news' ? '/' + gNewsToLoad : '';
	document.location.hash = '#' + id.replace('content_', '') + subSection;
}

function showSection(id) {
	showSectionNoLoad(id);

	if (gAuthenticated) {
		if (id == "content_news") {
			newsSubMenu(gNewsToLoad);
		} else if (id == "content_friends") {
			loadUsers();
		} else if (id == "content_subscriptions") {
			loadSubscriptions();
		}
	}
}

function newsSubMenuNoLoad(section) {
	gNewsToLoad = section;
	$(".subMenu").removeClass("selected");
	$("#submenu_news_" + section).addClass("selected");
	showSectionNoLoad('content_news');
}

function newsSubMenu(section) {
	newsSubMenuNoLoad(section);
	loadNews();
}

function makeEditableNode(node, getValue, setValue, callback) {
	$(node).click(function() {
		if (!$(node).data('original')) {
			var original = getValue(node);
			$(node).data('original', original);
			$(node).empty();
			var input = document.createElement('textarea');
			$(input).css({width: '100%', margin: '0', padding: '0'});
			$(input).val(original);
			$(node).append(input);

			function finishEdit() {
				var newValue = $(input).val();
				$(node).empty();
				$(node).data('original', null);
				setValue(node, newValue);
			}

			function cancelEdit() {
				var originalValue = $(node).data('original');
				$(node).empty();
				$(node).data('original', null);
				setValue(node, originalValue);
			}

			function startEdit() {
				$(input).attr('disabled', 'disabled');
				callback($(input).val(), finishEdit, cancelEdit);
			}

			$(input).keydown(function(event) {
				if (event.keyCode == 27) {
					// escape
					cancelEdit();
				} else if (event.keyCode == 13) {
					// enter
					startEdit();
				}
			});
			$(input).blur(function() {
				cancelEdit();
			});

			$(input).focus();
		}
	});
}

function makeSubscriptionNodes(subscription, indent) {
	var nodes = [];

	if (subscription != null) {
		var tr = document.createElement('tr');
		var td = document.createElement('td');
		$(td).text(subscription.name || "Unnamed");
		$(td).css('padding-left', (indent * 2) + 'em');
		function getName(node) {
			return $(node).text();
		}
		function setName(node, value) {
			$(node).text(value);
		}
		makeEditableNode(td,
			getName,
			setName,
			function(newValue, editSuccess, editFail) {
			$.ajax({
				type: "POST",
				url: "updateSubscription",
				data: { id: subscription.id, name: newValue },
				dataType: 'json',
			}).done(function(data) {
				updateError(data);
				if (data.affectedRows > 0) {
					editSuccess();
				} else {
					editFail();
				}
			}).fail(function() {
				editFail();
			});
		});
		$(tr).append(td);

		td = document.createElement('td');
		function getUrl(node) {
			return $(node).children().first().text();
		}
		function setUrl(node, url) {
			if (url) {
				var a = document.createElement('a');
				$(a).attr('href', url);
				$(a).text(url);
				$(node).css('max-width', '5%');
				$(node).append(a);
			}
		}
		setUrl(td, subscription.feedUrl);
		makeEditableNode(td, getUrl, setUrl, function(newValue, editSuccess, editFail) {
			$.ajax({
				type: "POST",
				url: "updateSubscription",
				data: { id: subscription.id, url: newValue },
				dataType: 'json',
			}).done(function(data) {
				updateError(data);
				if (data.affectedRows > 0) {
					editSuccess();
				} else {
					editFail();
				}
			}).fail(function() {
				editFail();
			});
		});
		$(tr).append(td);

		td = document.createElement('td');
		if (subscription.error) {
			$(td).text("Error: " + subscription.error);
			$(td).css('color', 'red');
		} else if (subscription.lastUpdate) {
			$(td).text("Last updated: " + new Date(subscription.lastUpdate * 1000));
		}
		if (subscription.recommendedUrl) {
			var div = document.createElement('div');
			$(div).css('color', 'red');
			$(div).text('Recommended URL: ' + subscription.recommendedUrl);
			$(td).append(div);

			var button = document.createElement('input');
			$(button).attr('type', 'button');
			$(button).attr('value', 'Fix URL');
			$(button).click(function() {
				$.ajax({
					type: "POST",
					url: "updateSubscription",
					data: { id: subscription.id, url: subscription.recommendedUrl },
					dataType: 'json',
				}).done(function(data) {
					updateError(data);
					loadSubscriptions();
				});
			});
			$(td).append(button);
		}
		$(tr).append(td);

		td = document.createElement('td');
		var button = document.createElement('input');
		$(button).attr('type', 'button');
		$(button).attr('value', 'Delete');
		$(button).click(function() {
			$.ajax({
				type: "POST",
				url: "deleteSubscription",
				data: { id: subscription.id },
				dataType: 'json',
			}).done(function(data) {
				updateError(data);
				loadSubscriptions();
			});
		});
		$(td).append(button);
		$(tr).append(td);
		nodes.push(tr);
	}

	gSubscriptions.forEach(function(other) {
		if ((subscription == null && other.parent == null) || (subscription != null && other.parent == subscription.id)) {
			nodes.push(makeSubscriptionNodes(other, indent + 1));
		}
	});

	return nodes;
}

function makeSubscriptionTreeNode(parent, subscription) {
	var div = document.createElement('div');
	var name = document.createElement('span');
	$(name).text(subscription.name || subscription.feedUrl);
	$(name).addClass("name");
	$(div).append(name);
	var count = document.createElement('span');
	$(count).addClass("count");
	$(div).append(count);
	var children = [];
	gSubscriptions.forEach(function(other) {
		if (other.parent == subscription.id) {
			children.push(other);
		}
	});
	children.sort(function(a, b) { return a.name < b.name; });
	var totalUnreadCount = subscription.unreadCount;
	children.forEach(function(child) {
		totalUnreadCount += makeSubscriptionTreeNode(div, child);
	});
	if (totalUnreadCount > 0) {
		$(count).text(' (' + totalUnreadCount + ')');
		$(div).addClass("unread");
	}
	$(div).click(function(event) {
		if ($(div).hasClass("selected")) {
			$(".subscriptionTree div").removeClass("selected");
			gSelectedSubscription = null;
		} else {
			$(".subscriptionTree div").removeClass("selected");
			$(div).addClass("selected");
			gSelectedSubscription = subscription;
		}
		loadNews();
		event.stopPropagation();
	});
	if (gSelectedSubscription != null && subscription.id == gSelectedSubscription.id) {
		$(div).addClass("selected");
		gSelectedSubscription = subscription;
		if (totalUnreadCount == 0 && gShowOnlyUnreadSubscriptions) {
			gSelectedSubscription = null;
		}
	}

	if (!gShowOnlyUnreadSubscriptions || totalUnreadCount > 0) {
		$(parent).append(div);
	}
	return totalUnreadCount;
}

function makeSubscriptionTree() {
	$(gSubscriptionTree).empty();
	var div = document.createElement('div');
	$(div).addClass('subscriptionTreeHeading');
	$(div).text(gShowOnlyUnreadSubscriptions ? "Unread Subscriptions" : "All Subscriptions");
	$(div).click(function() {
		gShowOnlyUnreadSubscriptions = !gShowOnlyUnreadSubscriptions;
		loadSubscriptions();
	});
	$(gSubscriptionTree).append(div);

	gSubscriptions.forEach(function(subscription) {
		if (subscription.parent == null) {
			 makeSubscriptionTreeNode(gSubscriptionTree, subscription);
		}
	});
}

function loadSubscriptions() {
	$("#subscriptions").empty();
	$("#subscriptions").append("<li>Loading...</li>");

	$(gSubscriptionTree).empty();
	$(gSubscriptionTree).append('<div>Loading subscriptions...</div>');

	$.ajax({
		type: "POST",
		url: "getSubscriptions",
		dataType: 'json',
	}).done(function(data) {
		updateError(data);
		gSubscriptions = data['subscriptions'];
		$("#subscriptions").empty();
		var table = document.createElement('table');
		$(table).addClass('wide');
		var tr = document.createElement('tr');
		['Name', 'Feed URL', 'Status', 'Actions'].forEach(function(heading) {
			var th = document.createElement('th');
			$(th).text(heading);
			$(tr).append(th);
		});
		$(table).append(tr);
		makeSubscriptionNodes(null, 0).forEach(function(row) {
			$(table).append(row);
		});
		makeSubscriptionTree();
		$("#subscriptions").append(table);
		['unread', 'all', 'shared', 'friends', 'starred'].forEach(function(type) {
			$("#count_" + type).text(data[type] > 0 ? data[type] : '');
		});
	});
}

function addFriend(user) {
	$.ajax({
		type: "POST",
		url: "addFriend",
		data: {'secret': user.secret},
		dataType: "json",
	}).done(function(data) {
		updateError(data);
		loadUsers();
	});
}

function removeFriend(user) {
	if (confirm('Are you sure you want to remove your friend "' + user.username + '"?')) {
		$.ajax({
			type: "POST",
			url: "removeFriend",
			data: {'id': user.id},
			dataType: "json",
		}).done(function(data) {
			updateError(data);
			loadUsers();
		});
	}
}

function loadUsers() {
	$("#users").empty();
	$("#users").append("<div>Loading...</div>");
	$.ajax({
		type: "POST",
		url: "getUsers",
		dataType: "json",
	}).done(function(data) {
		updateError(data);
		var table = document.createElement('table');
		$(table).addClass('wide');
		var row = document.createElement('tr');
		['Name', 'Privacy', 'Status', 'Available Actions'].forEach(function(heading) {
			var th = document.createElement('th');
			$(th).text(heading);
			$(row).append(th);
		});
		$(table).append(row);
		data.users.forEach(function(user) {
			row = document.createElement('tr');
			var td = document.createElement('td');
			$(td).text(user.username || "Anonymous");
			if (!user.username) {
				$(td).css('font-style', 'italic');
			}
			$(row).append(td);

			td = document.createElement('td');
			$(td).text(user.public ? "public" : "private");
			$(row).append(td);

			td = document.createElement('td');
			if (user.isFriend && user.isTheirFriend) {
				$(td).text("mutual friends");
			} else if (user.isFriend && !user.isTheirFriend) {
				$(td).text("your friend");
			} else if (!user.isFriend && user.isTheirFriend) {
				$(td).text("you are their friend");
			} else {
				$(td).text("not friends");
			}
			$(row).append(td);

			td = document.createElement('td');
			if (user.isFriend) {
				var button = document.createElement('input');
				$(button).attr('type', 'button');
				$(button).attr('value', 'Remove Friend');
				$(button).click(function() { removeFriend(user); });
				$(td).append(button);
			} else {
				var button = document.createElement('input');
				$(button).attr('type', 'button');
				$(button).attr('value', 'Add Friend');
				$(button).click(function() { addFriend(user); });
				$(td).append(button);
			}
			$(row).append(td);

			$(table).append(row);
		});
		$("#users").empty();
		$("#users").append(table);
	});
}

function setPreferences() {
	var newName = $("#name").val();
	var newPublic = $("#public").is(":checked");
	$("#user_apply").get().disabled = true;
	$.ajax({
		type: "POST",
		url: "setPreferences",
		data: {'username': newName, 'public': newPublic},
		dataType: 'json',
	}).done(function(data) {
		updateError(data);
		if (data.affectedRows > 0) {
			$("#display_name").text(newName);
		}
	}).fail(function(xhr, status) {
	}).always(function(data) {
		$("#user_apply").get().disabled = false;
	});
}

function addSubscription() {
	var feedUrl = $("#feed_url").val();
	$("#feed_url").val("");
	$.ajax({
		type: "POST",
		url: "addSubscription",
		data: { feedUrl: feedUrl },
		dataType: 'json',
	}).done(function(data) {
		updateError(data);
		loadSubscriptions();
	});
}

function markAllRead() {
	if (confirm('Really?')) {
		$.ajax({
			type: "POST",
			url: "markAllRead",
			data: {},
			dataType: 'json',
		}).done(function(data) {
			updateError(data);
			loadNews();
		});
	}
}

function refreshFeedHandler() {
	var subscription = gSubscriptionsToFetch.pop();
	if (subscription != null) {
		$.ajax({
			type: "POST",
			url: "fetchFeed",
			data: { feedUrl: subscription.feedUrl },
			dataType: 'json',
		}).done(function(data) {
			updateError(data);
		}).fail(function(xhr, status) {
			console.debug(subscription.feedUrl + " - " + status);
		}).always(function() {
			gSubscriptionsFetchedCount++;
			$("#feed_message").text("Loading..." + gSubscriptionsFetchedCount + " / " + gSubscriptionsToFetchCount);
			refreshFeedHandler();
		});
	} else {
		if (--gWorkerCount == 0) {
			loadNews();
		}
	}
}

function updateError(data) {
	if (data.error) {
		var node = document.createElement('div');
		$(node).text(data.error);
		$(node).addClass("exception");
		$("#error_contents").append(node);
		node = document.createElement('div');
		$(node).text(data.traceback);
		$(node).addClass("traceback");
		$("#error_contents").append(node);
		$("#error").show();
	}
}

function hideErrors() {
	$("#error").hide();
	$("#error_contents").empty();
}

function getSelectedSubscriptions() {
	var selected = [];

	function addSelectedSubscription(subscription) {
		if (subscription.feedUrl != null) {
			selected.push(subscription.feedUrl);
		}
		gSubscriptions.forEach(function(other) {
			if (other.parent == subscription.id) {
				addSelectedSubscription(other);
			}
		});
	}

	if (gSelectedSubscription != null) {
		addSelectedSubscription(gSelectedSubscription);
	}

	return selected;
}

function loadNews() {
	loadSubscriptions();
	$("#articles").empty();
	$("#feed_message").show();
	$("#feed_message").text("Loading...");
	$.ajax({
		type: "POST",
		url: "getNews",
		data: {'what': gNewsToLoad, 'feeds': getSelectedSubscriptions()},
		dataType: 'json',
		timeout: 15000,
	}).done(function(data) {
		updateError(data);
		gNews = data;
		gCursorIndex = -1;
		gFocused = -1;
		gSelected = -1;
		$("#articles").empty();
		$("#feed_message").hide();
		var allEntries = []
		data.items.forEach(function(article) {
			$("#articles").append(makeArticleNode(article));
		});
		if (data.items.length == 0) {
			$("#articles").append("<div class='noNewsIsGoodNews'>You've read all of the news that there is.  Good job!</div>");
		}
		if (data.more) {
			$("#articles").append("<div class='moreNews'>There is more news to be read, but there's no way to access it right now.  Maybe read some of the news above first and refresh to get more.</div>");
		}
	});
}

function updateUnreadCount(feedUrl, count) {
	var totalUnreadCount = 0;
	gSubscriptions.forEach(function(subscription) {
		if (subscription.feedUrl == feedUrl) {
			subscription.unreadCount += count;
		}
	});
	makeSubscriptionTree();
}

function makeArticleNode(article) {
	var entryDiv = document.createElement('div');
	$(entryDiv).addClass('article');

	var headingDiv = document.createElement('div');
	$(headingDiv).addClass("heading");
	var starredButton = $('<div class="iconButton star" />');
	$(headingDiv).append(starredButton);
	var feedName = document.createElement('span');
	$(feedName).addClass("feedName");
	if (article.feedName) {
		$(feedName).text(article.feedName);
	} else if (article.sharedBy) {
		$(feedName).text("Shared by " + article.sharedBy);
	} else {
		$(feedName).text("???");
	}
	$(headingDiv).append(feedName);
	if (article.published) {
		var publishedSpan = document.createElement('span');
		$(publishedSpan).addClass("date");
		$(publishedSpan).text(new Date(article.published * 1000).toLocaleString());
		$(headingDiv).append(publishedSpan);
	}
	if (article.share) {
		if (article.sharedBy) {
			var sharedBy = document.createElement('span');
			$(sharedBy).addClass("sharedBy");
			$(sharedBy).text(article.sharedBy);
			$(headingDiv).append(sharedBy);
		} else {
			var sharedBy = document.createElement('span');
			$(sharedBy).addClass("sharedBy");
			$(sharedBy).html("<i>Anonymous</i>");
			$(headingDiv).append(sharedBy);
		}
	}
	var subjectDiv = document.createElement('span');
	$(subjectDiv).addClass("title");
	$(subjectDiv).html(article.title);
	$(headingDiv).append(subjectDiv);
	var index = $("#articles").children().length;
	$(headingDiv).click(function() {
		selectArticle(index, true);
	});
	$(entryDiv).append(headingDiv);

	var expand = document.createElement('div');
	$(expand).addClass('expand');

	if (article.sharedBy != null) {
		var div = document.createElement('div');
		var span = document.createElement('span');
		$(span).text("Shared by ");
		$(div).append(span);
		span = document.createElement('span');
		$(span).text(article.sharedBy);
		$(span).addClass("sharer");
		$(div).append(span);
		if (article.sharedNote) {
			span = document.createElement('span');
			$(span).text(article.sharedNote);
			$(span).addClass("shareNote");
			$(div).append(span);
		}
		$(expand).append(div);
	}

	var link = document.createElement('a');
	$(link).attr('href', article.link || article.id);
	$(link).attr('target', '_blank');
	$(link).html(article.title);
	var titleDiv = document.createElement('div');
	$(titleDiv).addClass("title");
	$(titleDiv).append(link);
	$(expand).append(titleDiv);

	var summaryDiv = document.createElement('div');
	$(summaryDiv).addClass("summary");
	$(summaryDiv).html(article.summary);
	$(expand).append(summaryDiv);
	var readButton = $('<input type="button"></input>');
	$(expand).append(readButton);
	var shareNote = $('<input type="text"></input>');
	$(expand).append(shareNote);
	var shareButton = $('<input type="button"></input>');
	$(expand).append(shareButton);

	function addComment(container, time, username, comment) {
		var div = document.createElement('div');

		var span = document.createElement('span');
		$(span).text(new Date(time * 1000));
		$(span).addClass("time");
		$(div).append(span);

		span = document.createElement('span');
		$(span).text(username || "Anonymous");
		$(span).addClass("username");
		$(div).append(span);

		span = document.createElement('span');
		$(span).text(comment);
		$(span).addClass("comment");
		$(div).append(span);

		$(container).append(div);
	}

	if (article.isRead) {
		$(entryDiv).addClass('read');
	}

	if (article.share) {
		var commentsDiv = document.createElement('div');
		$(commentsDiv).addClass("comments");
		$(commentsDiv).append("<hr></hr>");
		$(commentsDiv).append("<div class='heading'>Comments:</div>");
		var commentsListDiv = document.createElement('div');
		article.comments.forEach(function(comment) {
			addComment(commentsListDiv, comment.time, comment.username, comment.comment);
		});
		$(commentsDiv).append(commentsListDiv);
		var commentArea = $('<textarea></textarea>');
		$(commentsDiv).append(commentArea);
		var commentButton = $('<input type="button" value="Add Comment"></input>');
		$(commentsDiv).append(commentButton);

		$(commentButton).click(function() {
			var comment = $(commentArea).val();
			$(commentButton).get().disabled = true;
			$.ajax({
				type: "POST",
				url: "addComment",
				data: {'share': article.share, 'comment': comment},
				dataType: 'json',
			}).done(function(data) {
				updateError(data);
				addComment(commentsListDiv, new Date().getTime() / 1000, $("#display_name").text(), comment);
				$(commentArea).val('');
			}).always(function(data) {
				$(commentButton).get().disabled = false;
			});
		});

		$(expand).append(commentsDiv);
	}
	$(entryDiv).append(expand);

	function updateReadButton(article, readButton) {
		$(readButton).val(article.isRead ? "Mark Unread" : "Mark Read");
	}
	function updateStarredButton(article, starredButton) {
		if (article.starred) {
			$(starredButton).addClass("selected");
		} else {
			$(starredButton).removeClass("selected");
		}
	}
	function updateShareButton(article, shareButton) {
		$(shareButton).val(article.shared ? "Unshare" : "Share");
	}
	function entryUpdated(data) {
		updateError(data);
		if ('isRead' in data) {
			updateUnreadCount(article.feed, article.isRead - data.isRead);
			article.isRead = data['isRead'];
			updateReadButton(article, readButton);
		}
		if ('starred' in data) {
			article.starred = data['starred'];
			updateStarredButton(article, starredButton);
		}
		if ('shared' in data) {
			article.shared = data['shared'];
			updateShareButton(article, shareButton);
		}
		if (article.isRead) {
			$(entryDiv).addClass('read');
		} else {
			$(entryDiv).removeClass('read');
		}
	}
	updateReadButton(article, readButton);
	updateStarredButton(article, starredButton);
	updateShareButton(article, shareButton);
	$(entryDiv).on('markRead', function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': article.feed, 'article': article.id, 'share': article.share || -1, 'isRead': true},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(entryDiv).on('toggleStarred', function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': article.feed, 'article': article.id, 'share': article.share || -1, 'starred': !article.starred},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(readButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': article.feed, 'article': article.id, 'share': article.share || -1, 'isRead': !article.isRead},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(starredButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': article.feed, 'article': article.id, 'share': article.share || -1, 'starred': !article.starred},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(shareButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setShared",
			data: {'feed': article.feed, 'article': article.id, 'share': !article.shared, 'note': $(shareNote).val()},
			dataType: 'json',
		}).done(entryUpdated);
	});

	return $(entryDiv);
}
