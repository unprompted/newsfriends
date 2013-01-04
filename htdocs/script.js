var gSubscriptions = [];
var gSubscriptionsToFetch = [];
var gWorkerCount = 0;
var gSubscriptionsToFetchCount = 0;
var gSubscriptionsFetchedCount = 0;
var gSelected = -1;

$(document).ready(function() {
	$("#add_subscription").click(addSubscription);
	$("#refresh_feeds").click(refreshFeeds);
	$("#mark_all_read_feeds").click(markAllRead);
	$("#user_apply").click(setPreferences);
	$("#hide_errors").click(hideErrors);

	if (gAuthenticated) {
		loadSubscriptions();
		loadNews();
		loadUsers();
	}

	makeMenu();
	showSection("content_news");
});

$(document).keypress(function(event) {
	if (event.target.tagName != 'TEXTAREA' && event.target.tagName != 'INPUT' && event.target.tagName != 'SELECT') {
		if ($("#content_news").is(":visible")) {
			var character = String.fromCharCode(event.keyCode);
			var lastSelected = gSelected;
			if (character == 'j') {
				if (gSelected == -1) {
					gSelected = 0;
				} else if (gSelected >= 0 && gSelected < $("#articles").children().length - 1) {
					gSelected++;
				}
			} else if (character == 'k') {
				if (gSelected == -1) {
					gSelected = $("#articles").children().length - 1;
				} else if (gSelected > 0 && gSelected < $("#articles").children().length) {
					gSelected--;
				}
			} else if (character == 'r') {
				refreshFeeds();
			} else if (character == 's') {
				$("#articles").children().eq(gSelected).trigger('toggleStarred');
			}

			if (lastSelected != gSelected) {
				$("#articles").children().eq(lastSelected).removeClass('selected');
				if (gSelected >= 0 && gSelected < $("#articles").children().length) {
					var toShow = $("#articles").children().eq(gSelected);
					toShow.addClass('selected');
					toShow.trigger('markRead');
					toShow.get(0).scrollIntoView(true);
				}
			}
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
}

function makeSubscriptionNode(subscription) {
	var li = document.createElement('li');
	$(li).attr('name', "subscription" + subscription.id);
	$(li).text(subscription.name || subscription.feedUrl);
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
	$(li).append(button);

	var children = [];
	gSubscriptions.forEach(function(other) {
		if (other.parent == subscription.id) {
			children.push(other);
		}
	});
	if (children.length) {
		var ul = document.createElement('ul');
		$(li).append(ul);
		children.forEach(function(child) {
			$(ul).append(makeSubscriptionNode(child));
		});
	}

	return li;
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
		data['subscriptions'].forEach(function(subscription) {
			if (subscription.parent == null) {
				$("#subscriptions").append(makeSubscriptionNode(subscription));
			}
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
			$(td).text(user.isFriend ? "friends" : "not friends");
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

function refreshFeeds() {
	$("#articles").empty();
	$("#feed_message").show();
	$("#feed_message").text("Loading...");
	loadNews();
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
		data.items.forEach(function(entry) {
			$("#articles").append(makeEntryNode(entry));
		});
	});
}

function makeEntryNode(entry) {
	var entryDiv = document.createElement('div');
	$(entryDiv).addClass('article');
	var titleDiv = document.createElement('div');
	$(titleDiv).css({'font-weight': 'bold'});
	if (entry.sharedBy != null) {
		var div = document.createElement('div');
		var span = document.createElement('span');
		$(span).text("Shared by: ");
		$(div).append(span);
		span = document.createElement('span');
		$(span).text(entry.sharedBy);
		$(span).css("font-weight", "bold");
		$(div).append(span);
		if (entry.sharedNote != null) {
			span = document.createElement('span');
			$(span).text(entry.sharedNote);
			$(span).css({'background-color': '#fff', 'border': '2px solid black', 'margin': '1em', 'padding': '0.5em', 'display': 'block'});
			$(div).append(span);
		}
		$(entryDiv).append(div);
	}
	var expand = document.createElement('div');
	$(expand).addClass('expand');
	var summaryDiv = document.createElement('div');
	var link = document.createElement('a');
	$(link).attr('href', entry.link || entry.id);
	$(link).attr('target', '_blank');
	$(link).html(entry.title);
	$(titleDiv).append(link);
	$(summaryDiv).html(entry.summary);
	$(entryDiv).append(titleDiv);
	$(entryDiv).append(expand);
	$(expand).append(summaryDiv);
	var readButton = $('<input type="button"></input>');
	$(expand).append(readButton);
	var starredButton = $('<input type="button"></input>');
	$(expand).append(starredButton);
	var shareNote = $('<input type="text"></input>');
	$(expand).append(shareNote);
	var shareButton = $('<input type="button"></input>');
	$(expand).append(shareButton);

	if (entry.share) {
		var commentsDiv = document.createElement('div');
		entry.comments.forEach(function(comment) {
			var div = document.createElement('div');
			$(div).text('<' + (comment.username || "Anonymous") + '> ' + comment.comment);
			$(commentsDiv).append(div);
		});
		var commentArea = $('<textarea></textarea>');
		$(commentsDiv).append(commentArea);
		var commentButton = $('<input type="button" value="Add Comment"></input>');
		$(commentsDiv).append(commentButton);

		$(commentButton).click(function() {
			$.ajax({
				type: "POST",
				url: "addComment",
				data: {'share': entry.share, 'comment': $(commentArea).val()},
				dataType: 'json',
			}).done(function(data) {
				updateError(data);
				$(commentArea).val('');
			});
		});

		$(expand).append(commentsDiv);
	}

	function updateReadButton(entry, readButton) {
		$(readButton).val(entry.isRead ? "Mark Unread" : "Mark Read");
	}
	function updateStarredButton(entry, starredButton) {
		$(starredButton).val(entry.starred ? "Remove Star" : "Add Star");
	}
	function updateShareButton(entry, shareButton) {
		$(shareButton).val(entry.shared ? "Unshare" : "Share");
	}
	function entryUpdated(data) {
		updateError(data);
		if ('isRead' in data) {
			entry.isRead = data['isRead'];
			updateReadButton(entry, readButton);
		}
		if ('starred' in data) {
			entry.starred = data['starred'];
			updateStarredButton(entry, starredButton);
		}
		if ('shared' in data) {
			entry.shared = data['shared'];
			updateShareButton(entry, shareButton);
		}
		if (entry.isRead) {
			$(entryDiv).addClass('read');
		} else {
			$(entryDiv).removeClass('read');
		}
	}
	updateReadButton(entry, readButton);
	updateStarredButton(entry, starredButton);
	updateShareButton(entry, shareButton);
	$(entryDiv).on('markRead', function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': entry.feed, 'article': entry.id, 'share': entry.shared ? -1 : entry.share, 'isRead': true},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(entryDiv).on('toggleStarred', function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': entry.feed, 'article': entry.id, 'share': entry.shared ? -1 : entry.share, 'starred': !entry.starred},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(readButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': entry.feed, 'article': entry.id, 'share': entry.shared ? -1 : entry.share, 'isRead': !entry.isRead},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(starredButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': entry.feed, 'article': entry.id, 'share': entry.shared ? -1 : entry.share, 'starred': !entry.starred},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(shareButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setShared",
			data: {'feed': entry.feed, 'article': entry.id, 'share': entry.shared ? -1 : entry.share, 'share': !entry.shared, 'note': $(shareNote).val()},
			dataType: 'json',
		}).done(entryUpdated);
	});

	return $(entryDiv);
}
