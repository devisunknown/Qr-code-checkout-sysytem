import re

with open('kitchendashboard.html', 'r') as f:
    content = f.read()

lines = content.splitlines(True)
out = []
i = 0
while i < len(lines):
    line = lines[i]
    if '<div class="bg-surface-container p-6 rounded-2xl border-2' in line and '{% if loop.first %}' in line:
        # Found the start of the block.
        out.append('<div class="bg-surface-container p-6 rounded-2xl border-2 border-outline-variant">\n')
        out.append('<div class="flex justify-between items-center mb-4">\n')
        out.append('    <h3 class="font-headline-md text-headline-md">Table {{ table.grouper.number }}</h3>\n')
        out.append('</div>\n')
        # skip the old lines
        i += 1  # skip the div line we matched
        if i < len(lines) and '<div class="flex justify-between items-center mb-4">' in lines[i]:
            i += 1
        if i < len(lines) and '<h3 class="font-headline-md text-headline-md">Table {{ table.grouper.number }}</h3>' in lines[i]:
            i += 1
        while i < len(lines):
            if lines[i].strip() == '</div>':
                i += 1
                break
            i += 1
        continue
    else:
        out.append(line)
        i += 1

with open('kitchendashboard.html', 'w') as f:
    f.writelines(out)
print('Replacement done')
