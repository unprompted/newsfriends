(function(window, document, req_version, callback, $, script, done, readystate) {
	// If jQuery isn't loaded, or is a lower version than specified, load the
	// specified version and call the callback, otherwise just call the callback.
	if (!($ = window.jQuery) || req_version > $.fn.jquery || callback($)) {
		// Create a script element.
		script = document.createElement( 'script' );
		script.type = 'text/javascript';
		
		// Load the specified jQuery from the Google AJAX API server (minified).
		script.src = 'http://ajax.googleapis.com/ajax/libs/jquery/' + req_version + '/jquery.min.js';
		
		// When the script is loaded, remove it, execute jQuery.noConflict(true)
		// on the newly-loaded jQuery (thus reverting any previous version to its
		// original state), and call the callback with the newly-loaded jQuery.
		script.onload = script.onreadystatechange = function() {
			if (!done && (!( readystate = this.readyState)
				|| readystate == 'loaded' || readystate == 'complete')) {
				
				callback(($ = window.jQuery).noConflict(1), done = 1);
				$(script).remove();
			}
		};

		// Add the script element to either the head or body, it doesn't matter.
		document.documentElement.childNodes[0].appendChild(script);
	}
})(
	window,
	document,

	// Minimum jQuery version required. Change this as-needed.
	'1.3.2',
	
	// Your jQuery code goes inside this callback. $ refers to the jQuery object,
	// and L is a boolean that indicates whether or not an external jQuery file
	// was just "L"oaded.
	function($, L) {
		var div = document.createElement('div');
		$(div).css({
			position: 'fixed',
			left: '0%',
			top: '0%',
			width: '100%',
			height: '100%',
			'z-index': 1000,
			'background-color': '#888',
			opacity: '0.5',
			filter: 'alpha(opacity=50)',
		});
		var frame = document.createElement('iframe');
		$(frame).attr('src', 'http://www.unprompted.com/news/test/share?url=' + encodeURIComponent(document.location.href) + '&title=' + encodeURIComponent(document.title));
		$(frame).css({
			position: 'fixed',
			left: '10%',
			top: '10%',
			width: '80%',
			height: '80%',
			'z-index': 1001,
		});
		$(div).hide();
		$(div).fadeIn(750);
		$(div).click(function() {
			$(div).remove();
			$(frame).remove();
		});
		$(document.body).append(div);
		$(document.body).append(frame);
	}
);
