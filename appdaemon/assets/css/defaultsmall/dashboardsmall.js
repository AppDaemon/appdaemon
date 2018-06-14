window.onload = function(){
	console.log("Js onLoad");
	clearIconAbsolute();
	h2IconSize();
    mediaButtonsPosition();
//    mediaTitlePosition();
	//disable scrollbars
//	document.body.css("overflow", "hidden");
}

function clearIconAbsolute(){
	var sheet = document.styleSheets[0];
	var rules = sheet.cssRules || sheet.rules;
	console.log("Extracted CSS rules");
	for(var i=0; i < rules.length; i++){
		//console.log("Looking at "+rules[i].selectorText);
		//do a regex to see if it's 
		// .widget-javascript-default-.* .icon
		if(/\.widget-(javascript|baseswitch|basejavascript)-default-.* \.icon/.test(rules[i].selectorText)){
			console.log("Found "+rules[i].selectorText);
			rules[i].style['position'] = "";
		}
		if(/\.widget-(basedisplay)-default-.* \.valueunit/.test(rules[i].selectorText)){
			console.log("Found "+rules[i].selectorText);
			rules[i].style['position'] = 'absolute';
		}
		if(rules[i].selectorText == 'body'){
			rules[i].style['overflow'] = 'hidden';
			rules[i].style['-webkit-touch-callout'] = 'none';
			rules[i].style['-webkit-user-select'] = 'none';
			rules[i].style['-khtml-user-select'] = 'none';
			rules[i].style['-moz-user-select'] = 'none';
			rules[i].style['-ms-user-select'] = 'none';
			rules[i].style['user-select'] = 'none';
		}
	} 
}

function h2IconSize(){
	var sheet = document.styleSheets[0];
        var rules = sheet.cssRules || sheet.rules;
        console.log("Extracted CSS rules");
        for(var i=0; i < rules.length; i++){
		if(/h2/.test(rules[i].selectorText)){
			console.log("Found "+rules[i].selectorText);
			rules[i].style['font-size'] = '250%';
		}
	}
}
function mediaButtonsPosition(){
	var sheet = document.styleSheets[0];
        var rules = sheet.cssRules || sheet.rules;
        console.log("Extracted CSS rules");
        for(var i=0; i < rules.length; i++){
		if(/\.widget-basemedia-default-.* \.(next|play|previous)/.test(rules[i].selectorText)){
			console.log("Found "+rules[i].selectorText);
			rules[i].style['top'] = '180px';
		}
	}
}

function mediaTitlePosition(){
	var sheet = document.styleSheets[0];
        var rules = sheet.cssRules || sheet.rules;
        console.log("Extracted CSS rules");
        for(var i=0; i < rules.length; i++){
		if(/\.widget-basemedia-default-.* \.media_title/.test(rules[i].selectorText)){
			console.log("Found "+rules[i].selectorText);
			rules[i].style['top'] = '30px';
		}
	}
}

