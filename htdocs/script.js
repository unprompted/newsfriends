var gSubscriptions = [];

$(document).ready(function() {
	$("#add_subscription").click(addSubscription);
	$("#refresh_feeds").click(refreshFeeds);
	$("#get_news").click(loadNews);

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

function updateEntryStatus(div, entry, readButton, starredButton) {
	function updateReadButton(entry, readButton) {
		$(readButton).val(entry.read ? "Mark Unread" : "Mark Read");
	}
	function updateStarredButton(entry, starredButton) {
		$(starredButton).val(entry.starred ? "Remove Star" : "Add Star");
	}
	function entryUpdated(data) {
		entry.read = data['read'];
		entry.starred = data['starred'];
		updateReadButton(entry, readButton);
		updateStarredButton(entry, starredButton);
	}
	updateReadButton(entry, readButton);
	updateStarredButton(entry, starredButton);
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
			var entryDiv = document.createElement('div');
			var titleDiv = document.createElement('h2');
			var summaryDiv = document.createElement('div');
			$(titleDiv).html(entry.title);
			$(summaryDiv).html(entry.summary);
			$(entryDiv).append(titleDiv);
			$(entryDiv).append(summaryDiv);
			$(entryDiv).css({border: "1px solid black", padding: "1em", margin: "1em", "background-color": "#eef"});
			var readButton = $('<input type="button"></input>');
			var starredButton = $('<input type="button"></input>');
			updateEntryStatus(entryDiv, entry, readButton, starredButton);
			$(entryDiv).append(readButton);
			$(entryDiv).append(starredButton);
			$("#articles").append(entryDiv);
		});
	});
}
