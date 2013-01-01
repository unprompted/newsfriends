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
	$("#set_name").click(setName);

	if (gAuthenticated) {
		loadSubscriptions();
		loadNews();
	}
});

$(document).keypress(function(event) {
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
});

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
		gSubscriptions = data['subscriptions'];
		$("#subscriptions").empty();
		data['subscriptions'].forEach(function(subscription) {
			if (subscription.parent == null) {
				$("#subscriptions").append(makeSubscriptionNode(subscription));
			}
		});
	});
}

function setName() {
	var newName = $("#name").val();
	$("#set_name").get().disabled = true;
	$.ajax({
		type: "POST",
		url: "setName",
		data: {'name': newName},
		dataType: 'json',
	}).always(function(data) {
		$("#set_name").get().disabled = false;
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
			console.debug(data);
			loadNews();
		});
	}
}

function refreshFeeds() {
	$("#articles").empty();
	$("#feed_message").show();
	$("#feed_message").text("Loading...");
	gSubscriptionsToFetch = [];
	gSubscriptions.forEach(function(subscription) {
		if (subscription.feedUrl) {
			gSubscriptionsToFetch.push(subscription);
		}
	});
	gSubscriptionsToFetchCount = gSubscriptionsToFetch.length;
	gSubscriptionsFetchedCount = 0;
	gWorkerCount = 4;
	for (var i = gWorkerCount; i > 0; i--) {
		refreshFeedHandler();
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
			if (data.error) {
				console.debug(data.error);
				console.debug(data.traceback);
			}
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

function loadNews() {
	$.ajax({
		type: "POST",
		url: "getNews",
		data: {},
		dataType: 'json',
		timeout: 15000,
	}).done(function(data) {
		if (data.error) {
			$("#error_message").text(data.error);
			$("#error_traceback").text(data.traceback);
			$("#error").show();
		} else {
			$("#error").hide();
			gSelected = -1;
			$("#articles").empty();
			$("#feed_message").hide();
			var allEntries = []
			data.items.forEach(function(entry) {
				$("#articles").append(makeEntryNode(entry));
			});
		}
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
	var starredButton = $('<input type="button"></input>');
	var shareButton = $('<input type="button"></input>');
	$(expand).append(readButton);
	$(expand).append(starredButton);
	$(expand).append(shareButton);

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
			data: {'feed': entry.feed, 'article': entry.id, 'isRead': true},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(entryDiv).on('toggleStarred', function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': entry.feed, 'article': entry.id, 'starred': !entry.starred},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(readButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': entry.feed, 'article': entry.id, 'isRead': !entry.isRead},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(starredButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'feed': entry.feed, 'article': entry.id, 'starred': !entry.starred},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(shareButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setShared",
			data: {'feed': entry.feed, 'article': entry.id, 'share': !entry.shared},
			dataType: 'json',
		}).done(entryUpdated);
	});

	return $(entryDiv);
}
