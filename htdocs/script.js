var gSubscriptions = [];

$(document).ready(function() {
	$("#add_subscription").click(addSubscription);
	$("#refresh_feeds").click(refreshFeeds);

	loadSubscriptions();
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
