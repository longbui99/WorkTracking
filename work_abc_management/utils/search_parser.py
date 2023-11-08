import re
import time
import json


def minify_response(res):
    return True


def get_search_request(string):
    res = {}
    truncate_regex = '[:]'
    parser = {
        'jql=': ('jql', -1, False),
        'chain': ('chain', 0, True),
        'sprint': ('sprint', 0, True),
        'favorite': ('favorite', 0, True),
        'today': ('today', 0, True),
        'tomorrow': ('tomorrow', 0, True),
        '[ \.]?mine[ \.]?': ('mine', 0, True),
        '\[[a-zA-Z0-9]+\]': ('project', 1, -1),
        '[a-zA-Z0-9]+-[0-9]+': ('task', 0, True),
        '[A-Z]{2,}': ('project', 0, True),
        '\[[a-zA-Z0-9]+-[a-zA-Z0-9]+\]': ('task', 1, -1),
        '>[a-zA-Z0-9@.]+<?': ('name', 1, True),
        '(p[0-9-/]{10}|p[0-9-/]{8})': ('personal', 1, True),
    }
    interator = re.finditer('(([a-zA-Z0-9]+-[0-9]+:?)|[A-Z]{2,}:?|\[[a-zA-Z0-9-]*\]|>[a-zA-Z0-9@.]+<?|[ \.]?(chain|mine|sprint|today|tomorrow\+?)[ \.]?|(p[0-9-/]{10}|p[0-9-/]{8})|favorite|jql=)', string)
    for_delete = []
    for match in interator:
        action = re.sub(truncate_regex, '', match.group())
        for_delete.append(match.span())
        for key in parser.keys():
            result = re.match(key, action)
            if result:
                detect = parser[key]
                if not isinstance(detect[2], bool):
                    res[detect[0]] = action[detect[1]: detect[2]]
                elif detect[2]:
                    res[detect[0]] = action[detect[1]: ]
                else:
                    res[detect[0]] = string[match.span()[1]:]
                break
    margin_left = 0
    for start, end in for_delete:
        string = string[:start - margin_left] + string[end - margin_left:]
        margin_left += end - start
    trimmed_string = string.strip().replace('.', '')
    if len(trimmed_string):
        res['text'] = trimmed_string

    return res