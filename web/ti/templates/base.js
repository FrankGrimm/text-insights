(function($) {
$(document).ready(function(){

    // tagcloud JS
    var switcher = $('<a href="javascript:void(0)" class="btn">Change appearance</a>').toggle(
        function(){
            $(".tags ul").hide().addClass("alt").fadeIn("fast");
        },
        function(){
            $(".tags ul").hide().removeClass("alt").fadeIn("fast");
        }
    );
    $('.tags').append(switcher);

    // create a sort by alphabet button
    var sortabc = $('<a href="javascript:void(0)" class="btn">Sort alphabetically</a>').toggle(
        function(){
            $(".tags ul li").tsort({order:"asc"});
        },
        function(){
            $(".tags ul li").tsort({order:"desc"});
        }
        );
    $('.tags').append(sortabc);

    // create a sort by alphabet button
    var sortstrength = $('<a href="javascript:void(0)" class="btn">Sort by strength</a>').toggle(
        function(){
            $(".tags ul li").tsort({order:"desc",attr:"class"});
        },
        function(){
            $(".tags ul li").tsort({order:"asc",attr:"class"});
        }
        );
    $('.tags').append(sortstrength);

    // http://stackoverflow.com/questions/5980237/show-back-to-top-link-element-using-jquery-when-you-scroll-down
    $(window).scroll(function() {
        if ($(this).scrollTop() > 400) {
            $('#jumpToTop:hidden').stop(true, true).fadeIn();
        } else {
            $('#jumpToTop').stop(true, true).fadeOut();
        }
    });
    $('#jumpToTop').hide();

    // AJAX activity display
    $('#ajaxload').hide();

    $(document).bind('ajaxStart', function() {
        console.log('ajaxStart');
        $('#ajaxload').show();
    }).bind('ajaxStop', function() {
        console.log('ajaxStop');
        $('#ajaxload').hide();
    });

    // setup datepicker defaults
    $.fn.datepicker.defaults.weekStart = 1; // week start = Monday
    $.fn.datepicker.defaults.format = "yyyy-mm-dd";
    $("input.datepicker").datepicker();

});
})(jQuery);
