
def parsing(syntax, text):
    pivot, index, final, final_key = 0, 0, [''], 0
    length, pasring_length = len(text), len(syntax)
    while index < length:
        for key in syntax.keys():
            if index + len(key) <= length:
                if text[index: index+len(key)] == key:
                    if len(final[final_key]) > 0:
                        if len(key) <= len(final[final_key]):
                            substr = text[pivot:index]
                            if len(substr):
                                res = f"{syntax[key][0]}{substr}{syntax[key][1]}"
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