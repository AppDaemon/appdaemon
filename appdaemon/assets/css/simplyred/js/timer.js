var now = new Date();
var hours = now.getHours();

//Keep in code - Written by Computerhope.com
//Place this script in your HTML heading section

document.bgColor="#CC9900";

//18-19 night
if (hours > 17 && hours < 20){
document.write ('<body style="background-color: black">');
}
//20-21 night
else if (hours > 19 && hours < 22){
document.write ('<body style="background-color: #111">');
}
//22-4 night
else if (hours > 21 || hours < 5){
document.write ('<body style="background-color: #333;">');
}
//9-17 day
else if (hours > 8 && hours < 18){
document.write ('<body style="background-color: #555">');
}
//7-8 day
else if (hours > 6 && hours < 9){
document.write ('<body style="background-color: #999">');}
//5-6 day
else if (hours > 4 && hours < 7){
document.write ('<body style="background-color: #C8C8C8">');
}
else {
document.write ('<body style="background-color: white">');
}
