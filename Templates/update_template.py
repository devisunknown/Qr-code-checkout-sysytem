import re

with open('kitchendashboard.html', 'r') as f:
    content = f.read()

lines = content.splitlines(True)
out = []
i = 0
while i < len(lines):
    line = lines[i]
    if '<div class="bg-surface-container p-6 rounded-2xl border-2 border-outline-variant">' in line:
        # Found start of table card.
        out.append(line)
        i += 1
        # Next line should be the flex div line.
        if i < len(lines) and '<div class="flex justify-between items-center mb-4">' in lines[i]:
            # We'll keep the flex div line but we need to modify its content.
            # Instead of just copying, we will output the flex div opening, then the h3, then the form, then closing div.
            out.append('<div class="flex justify-between items-center mb-4">\n')
            out.append('    <h3    '\n')
            # Actually easier: we will output the new block as described.
            out.append('    <h3 class="font-headline-md text-headline-md">Table {{ table.grouper.number }}</h3>\n')
            out.append('    <div>\n')
            out.append('        <form action="{% url \'mark_table_orders_ready\' table.grouper.id %}" method="post" class="ml-2">\n')
            out.append('            {% csrf_token %}\n')
            out.append('            <button type="submit" class="bg-primary text-on-primary font-bold py-1 px-3 rounded-xl">Done Preparing</button>\n')
            out.append('        </form>\n')
            out.append('    </div>\n')
            out.append('</div>\n')
            # Skip the original flex div line and the following lines until we see its closing </div>
            i += 1  # skip the flex div line we just processed
            # Now we need to skip the original h3 line and its closing </div>
            # The original pattern after flex div line is:
            #     <h3 class="font-headline-md text-headline-md">Table {{ table.grouper.number }}</h3>
            # </div>
            # So we skip two lines.
            if i < len(lines) and '<h3 class="font-headline-md text-headline-md">Table {{ table.grouper.number }}</h3>' in lines[i]:
                i += 1
            if i < len(lines) and lines[i].strip() == '</div>':
                i += 1
            continue
    else:
        out.append(line)
        i += 1

with open('kitchendashboard.html', 'w') as f:
    f.writelines(out)
print('Updated')
