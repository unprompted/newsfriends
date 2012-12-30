var gSubscriptions = [];

$(document).ready(function() {
	$("#add_subscription").click(addSubscription);
	$("#refresh_feeds").click(refreshFeeds);
	$("#get_news").click(loadNews);
	$("#set_name").click(setName);

	loadSubscriptions();
	loadNews();
});

function loadSubscriptions() {
	$("#subscriptions").empty();
	$("#subscriptions").append("<li>Loading...</li>");
	$.ajax({
		type: "POST",
		url: "getSubscriptions",
		dataType: 'json',
	}).done(function(data) {
		console.debug(data);
		gSubscriptions = data['subscriptions'];
		$("#subscriptions").empty();
		for (var i in data['subscriptions']) {
			var subscription = data['subscriptions'][i];
			var li = document.createElement('li');
			$(li).text(subscription.feedUrl);
			$("#subscriptions").append(li);
		}
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
		console.debug(data);
		loadSubscriptions();
	});
}

function refreshFeeds() {
	for (var i in gSubscriptions) {
		var subscription = gSubscriptions[i];
		$.ajax({
			type: "POST",
			url: "fetchFeed",
			data: { feedUrl: subscription.feedUrl },
			dataType: 'json',
		}).done(function(data) {
			console.debug(data);
		});
	}
}

function makeEntryNode(entry) {
	var entryDiv = document.createElement('div');
	var titleDiv = document.createElement('h2');
	var summaryDiv = document.createElement('div');
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
	$(titleDiv).html(entry.title);
	$(summaryDiv).html(entry.summary);
	$(entryDiv).append(titleDiv);
	$(entryDiv).append(summaryDiv);
	$(entryDiv).css({border: "1px solid black", padding: "1em", margin: "1em", "background-color": "#eef"});
	var readButton = $('<input type="button"></input>');
	var starredButton = $('<input type="button"></input>');
	var shareButton = $('<input type="button"></input>');
	$(entryDiv).append(readButton);
	$(entryDiv).append(starredButton);
	$(entryDiv).append(shareButton);

	function updateReadButton(entry, readButton) {
		$(readButton).val(entry.read ? "Mark Unread" : "Mark Read");
	}
	function updateStarredButton(entry, starredButton) {
		$(starredButton).val(entry.starred ? "Remove Star" : "Add Star");
	}
	function updateShareButton(entry, shareButton) {
		$(shareButton).val(entry.shared ? "Unshare" : "Share");
	}
	function entryUpdated(data) {
		if ('read' in data) {
			entry.read = data['read'];
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
	}
	updateReadButton(entry, readButton);
	updateStarredButton(entry, starredButton);
	updateShareButton(entry, shareButton);
	$(readButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'article': entry.id, 'read': !entry.read},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(starredButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setStatus",
			data: {'article': entry.id, 'starred': !entry.starred},
			dataType: 'json',
		}).done(entryUpdated);
	});
	$(shareButton).click(function() {
		$.ajax({
			type: "POST",
			url: "setShared",
			data: {'article': entry.id, 'share': !entry.shared},
			dataType: 'json',
		}).done(entryUpdated);
	});

	return $(entryDiv);
}

function loadNews() {
	$.ajax({
		type: "POST",
		url: "getNews",
		data: {},
		dataType: 'json',
	}).done(function(data) {
		$("#articles").empty();
		console.debug(data.items);
		var allEntries = []
		data.items.forEach(function(entry) {
			$("#articles").append(makeEntryNode(entry));
		});
	});
}
