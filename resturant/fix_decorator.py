with open('views.py', 'r') as f:
    lines = f.readlines()

i = 0
while i < len(lines):
    if lines[i].strip() == '@login_required' and i+1 < len(lines) and lines[i+1].strip() == '@login_required':
        # Remove the duplicate
        del lines[i+1]
        # do not increment i because we want to check again in case there are more duplicates
    else:
        i += 1

with open('views.py', 'w') as f:
    f.writelines(lines)
print('Fixed duplicate decorators')
