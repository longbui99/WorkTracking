
def md2json(data):
    lines = data.split('\n')
    res, key = dict(), ''
    for line in lines:
        line = line.strip()
        step = {}
        index = 1
        if line.startswith('#'):
            key = line[index:].strip()
            res[key] = []
            continue
        elif line.startswith('--- '):
            step['is_header'] = True
            index = 4
        elif line.startswith('* '):
            index, length = 3, len(line)
            while line[index] != ']':
                index+=1
            checkpoint = index + 1
            step['status'] = line[3:index]
            step['is_header'] = False
            while line[index] != ' ':
                index+=1
            step['addition'] = line[checkpoint: index]
        step['name'] = line[index:].strip(' :')
        res[key].append(step)
    return res