$(document).ready(function() {
	$("#add_subscription").click(addSubscription);

	loadSubscriptions();
});

function loadSubscriptions() {
	$.ajax({
		type: "POST",
		url: "getSubscriptions",
		dataType: 'json',
	}).done(function(data) {
		console.debug(data);
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
