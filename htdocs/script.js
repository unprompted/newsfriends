var gSubscriptions = [];
var gSubscriptionsToFetch = [];
var gWorkerCount = 0;
var gSubscriptionsToFetchCount = 0;
var gSubscriptionsFetchedCount = 0;
var gSelected = -1;

$(document).ready(function() {
	$("#add_subscription").click(addSubscription);
	$("#refresh_feeds").click(loadNews);
	$("#mark_all_read_feeds").click(markAllRead);
	$("#user_apply").click(setPreferences);
	$("#hide_errors").click(hideErrors);

	makeMenu();
	showSection("content_news");
});

function selectArticle(index) {
	if (index != gSelected) {
		$("#articles").children().eq(gSelected).removeClass('selected');
		gSelected = index;
		if (gSelected >= 0 && gSelected < $("#articles").children().length) {
			var toShow = $("#articles").children().eq(gSelected);
			toShow.addClass('selected');
			toShow.trigger('markRead');
			toShow.get(0).scrollIntoView(true);
		}
	}
}

$(document).keypress(function(event) {
	if (event.target.tagName != 'TEXTAREA' && event.target.tagName != 'INPUT' && event.target.tagName != 'SELECT') {
		if ($("#content_news").is(":visible")) {
			var character = String.fromCharCode(event.keyCode);
			var select = gSelected;
			if (character == 'j') {
				if (select == -1) {
					select = 0;
				} else if (select >= 0 && select < $("#articles").children().length - 1) {
					select++;
				}
			} else if (character == 'k') {
				if (select == -1) {
					select = $("#articles").children().length - 1;
				} else if (select > 0 && select < $("#articles").children().length) {
					select--;
				}
			} else if (character == 'r') {
				loadNews();
			} else if (character == 's') {
				$("#articles").children().eq(select).trigger('toggleStarred');
			}

			selectArticle(select);
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
	});
}

function showSection(id) {
	$(".menu").removeClass("selected");
	$(".content").hide();
	$('#' + id).show();
	$('#menu_' + id).addClass("selected");

	if (gAuthenticated) {
		if (id == "content_news") {
			loadNews();
		} else if (id == "content_friends") {
			loadUsers();
		} else if (id == "content_subscriptions") {
			loadSubscriptions();
		}
	}
}

function makeSubscriptionNodes(subscription, indent) {
	var nodes = [];

	if (subscription != null) {
		var tr = document.createElement('tr');
		var td = document.createElement('td');
		$(td).text(subscription.name || "Unnamed");
		$(td).css('padding-left', (indent * 2) + 'em');
		$(tr).append(td);

		td = document.createElement('td');
		if (subscription.feedUrl) {
			var a = document.createElement('a');
			$(a).attr('href', subscription.feedUrl);
			$(a).text(subscription.feedUrl);
			$(td).css('max-width', '5%');
			$(td).append(a);
		}
		$(tr).append(td);

		td = document.createElement('td');
		if (subscription.error) {
			$(td).text("Error: " + subscription.error);
			$(td).css('color', 'red');
		} else if (subscription.lastUpdate) {
			$(td).text("Last updated: " + new Date(subscription.lastUpdate * 1000));
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
				data: { feedUrl: subscription.feedUrl },
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

function loadSubscriptions() {
	$("#subscriptions").empty();
	$("#subscriptions").append("<li>Loading...</li>");
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
		$("#subscriptions").append(table);
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
			$(td).text(user.username);
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

function loadNews() {
	$("#articles").empty();
	$("#feed_message").show();
	$("#feed_message").text("Loading...");
	$.ajax({
		type: "POST",
		url: "getNews",
		data: {},
		dataType: 'json',
		timeout: 15000,
	}).done(function(data) {
		updateError(data);
		gSelected = -1;
		$("#articles").empty();
		$("#feed_message").hide();
		var allEntries = []
		data.items.forEach(function(article) {
			$("#articles").append(makeArticleNode(article));
		});
	});
}

function makeArticleNode(article) {
	var entryDiv = document.createElement('div');
	$(entryDiv).addClass('article');

	var headingDiv = document.createElement('div');
	$(headingDiv).addClass("heading");
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
	var subjectDiv = document.createElement('span');
	$(subjectDiv).addClass("title");
	$(subjectDiv).text(article.title);
	$(headingDiv).append(subjectDiv);
	var index = $("#articles").children().length;
	$(headingDiv).click(function() {
		selectArticle(index);
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
	var starredButton = $('<input type="button"></input>');
	$(expand).append(starredButton);
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
		$(starredButton).val(article.starred ? "Remove Star" : "Add Star");
	}
	function updateShareButton(article, shareButton) {
		$(shareButton).val(article.shared ? "Unshare" : "Share");
	}
	function entryUpdated(data) {
		updateError(data);
		if ('isRead' in data) {
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
			data: {'feed': article.feed, 'article': article.id, 'share': article.shared ? -1 : article.share, 'isRead': true},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(entryDiv).on('toggleStarred', function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': article.feed, 'article': article.id, 'share': article.shared ? -1 : article.share, 'starred': !article.starred},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(readButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': article.feed, 'article': article.id, 'share': article.shared ? -1 : article.share, 'isRead': !article.isRead},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(starredButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': article.feed, 'article': article.id, 'share': article.shared ? -1 : article.share, 'starred': !article.starred},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(shareButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setShared",
			data: {'feed': article.feed, 'article': article.id, 'share': article.shared ? -1 : article.share, 'share': !article.shared, 'note': $(shareNote).val()},
			dataType: 'json',
		}).done(entryUpdated);
	});

	return $(entryDiv);
}
