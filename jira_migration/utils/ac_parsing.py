import re

ac_rules = {
    '**': ['<b>', '</b>'],
    '*': ['<em>', '</em>'],
}

replace_rule = {
    '\n\n': '<br>',
    '\n': '<br>'
}

ac_unparsing_rules = [
    {'pattern': '<b>', 'value': '**'},
    {'pattern': '</b>', 'value': '**'},
    {'pattern': '</i>', 'value': '*'},
    {'pattern': "<i>", 'value': '*'},
    {'pattern': "&nbsp;", 'value': ' '},
]


def parsing(text):
    for rule in replace_rule.keys():
        text = text.replace(rule, replace_rule[rule])
    pivot, index, final, final_key = 0, 0, [''], 0
    length, pasring_length = len(text), len(ac_rules)
    while index < length:
        for key in ac_rules.keys():
            if index + len(key) <= length:
                if text[index: index + len(key)] == key:
                    if len(final[final_key]) > 0:
                        if len(key) <= len(final[final_key]):
                            substr = text[pivot:index]
                            if len(substr):
                                res = f"{ac_rules[key][0]}{substr}{ac_rules[key][1]}"
                            else:
                                res = key + key
                            final.append(res)
                            final[final_key] = final[final_key][0:-len(key)]
                        else:
                            final[final_key] += key
                    else:
                        final.append(text[pivot:index])
                        final.append(key)
                        final_key = len(final) - 1
                    index += len(key) - 1
                    pivot = index + 1
                    break
        index += 1
    if pivot != index:
        final.append(text[pivot:index])
    return "".join(final)


def unparsing(text):
    for syntax in ac_unparsing_rules:
        text = re.sub(syntax['pattern'], syntax['value'], text)
    index, pivot, length = 0, 0, len(text)
    while index < length:
        if text[index] in ("<", '&'):
            pivot = index
        elif text[index] in (">", ';'):
            text = text[:pivot] + text[index+1:]
            length -= (index-pivot + 1)
            index -= (index-pivot + 1)
        index += 1

    return text
