import re

ac_rules = {
    '**': ['<b>', '</b>'],
    '*': ['<em>', '</em>']
}

ac_unparsing_rules = [
    {'pattern': '<b>(.*)</b>', 'value': '**\\1**'},
    {'pattern': '<b style=".+">(.*)</b>', 'value': '**\\1**'},
    {'pattern': "</em>", 'value': '*'},
    {'pattern': "<em.+>", 'value': '*'},
    {'pattern': '<span style=".+">( )</span>', 'value': ' '},
    {'pattern': '<span style=".+">(.*)</span>', 'value': '\\1'},
]

def parsing(text):
    pivot, index, final, final_key = 0, 0, [''], 0
    length, pasring_length = len(text), len(ac_rules)
    while index < length:
        for key in ac_rules.keys():
            if index + len(key) <= length:
                if text[index: index+len(key)] == key:
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
                        final_key = len(final)-1
                    index += len(key)-1
                    pivot = index+1
                    break
        index += 1 
    return "".join(final)
    
def unparsing(text):
    for syntax in ac_unparsing_rules:
        text = re.sub(syntax['pattern'], syntax['value'], text)
    return text