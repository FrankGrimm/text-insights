from django import template

register = template.Library()

@register.simple_tag
def posttype(text):
    res = "icon-"
    if text == "status":
        res = res + "comment"
    elif text == "photo":
        res = res + "picture"
    elif text == "question":
        res = res + "question-sign"
    elif text == "video":
        res = res + "film"
    elif text == "link":
        res = res + "home"
    else:
        res = res + "play"
    return res

