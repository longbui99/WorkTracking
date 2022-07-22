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
        'chain': ('chain', 0, -1),
        'sprint': ('sprint', 0, -1),
        'mine': ('mine', 0, -1),
        '[A-Z]+-[0-9]+': ('ticket', 0, True),
        '[A-Z]{2}': ('project', 0, True),
        '<[a-zA-Z0-9]+-[a-zA-Z0-9]+>': ('ticket', 1, -1),
        '<[a-zA-Z0-9]+>': ('project', 1, -1),
        '~[a-zA-Z0-9@-_\.]+\.': ('name', 1, -1),
    }
    interator = re.finditer('(([A-Z]+-[0-9]+:?)|[A-Z]{3}:?|<[a-zA-Z0-9-]*>|~.*~|\.?(chain|mine|sprint\+?)\.?|jql=)', string)
    for_delete = []
    for match in interator:
        action = re.sub(truncate_regex, '', match.group())
        for_delete.append(match.span())
        for key in parser.keys():
            result = re.match(key, action)
            if result:
                detect = parser[key]
                print(key, '-', result, '-', detect)
                if detect[2] == -1:
                    res[detect[0]] = action[detect[1]: detect[2]]
                elif detect[2]:
                    res[detect[0]] = action
                else:
                    res[detect[0]] = string[match.span()[1]:]
                break
    margin_left = 0
    for start, end in for_delete:
        string = string[:start - margin_left] + string[end - margin_left:]
        margin_left += end - start
    trimmed_string = string.strip()
    if len(trimmed_string):
        res['text'] = trimmed_string

    return res

string = "mine sprint <ZIP>"
print(get_search_request(string))
