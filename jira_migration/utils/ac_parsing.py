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
    {'pattern': '<b>(.*)</b>', 'value': '**\\1**'},
    {'pattern': '<b style=".+">(.*)</b>', 'value': '**\\1**'},
    {'pattern': "</em>", 'value': '*'},
    {'pattern': "<em.+>", 'value': '*'},
    {'pattern': '<span style=".+">( )</span>', 'value': ' '},
    {'pattern': '<span style=".+">(.*)</span>', 'value': '\\1'},
]

def parsing(text):
    for rule in replace_rule.keys():
        text = text.replace(rule, replace_rule[rule])
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
    if pivot != index:
        final.append(text[pivot:index])
    return "".join(final)
    
def unparsing(text):
    for syntax in ac_unparsing_rules:
        text = re.sub(syntax['pattern'], syntax['value'], text)
    return text

# text = []
# text.append("After reloading pos session then pos square payment still keep the status and layout")
# text.append('Add field **Reason** with message: "Cannot process Payment"')
# text.append('Add the button "OK"')
# text.append('**Domain**: **C1** OR **C2** OR **C3**\n>>\nC1: The field **Warehouses** is unchecked.\n\nC2: The field **Warehouses** is checked but there is no selected warehouse.\n\nC3: The field **Warehouses** is checked and at least one warehouse is in active warehouses.\n')
# for txt in text:
#     print(txt)
#     print(parsing(txt))
#     print('-------------------------------------')