import sys

with open('kitchendashboard.html', 'r') as f:
    lines = f.readlines()

# Find the line numbers for the start of the table loop and the end of the table header block.
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if '{% for table in orders|groupby:"table_session.table" %}' in line:
        # We are at line 193 (0-index?). Keep the for line.
        new_lines.append(line)
        i += 1
        # Next line should be the div for each table.
        # Replace that div line and the following flex div and span.
        # Expect line: '<div class="bg-surface-container p-6 rounded-2xl border-2 {% if loop.first %}border-error ticket-urgent{% else %}border-outline-variant %}">'
        # We'll replace it with a simpler div.
        # Skip the existing div line.
        if i < len(lines):
            # Skip the old div line
            i += 1
        # Insert new div line
        new_lines.append('<div class="bg-surface-container p-6 rounded-2xl border-2 border-outline-variant">\n')
        # Next line should be the flex div line.
        if i < len(lines):
            # Skip the old flex div line
            i += 1
        # Insert new flex div with just the h3
        new_lines.append('<div class="flex justify-between items-center mb-4">\n')
        new_lines.append('    <h3 class="font-headline-md text-headline-md">Table {{ table.grouper.number }}</h3>\n')
        new_lines.append('</div>\n')
        # Now we should be at the line that starts the inner for loop: '{% for order in table.list %}'
        # Keep it as is.
        if i < len(lines):
            new_lines.append(lines[i])
            i += 1
        # Continue copying lines until we hit the matching endfor for the inner loop? Actually we need to copy until we reach the outer endfor.
        # We'll just copy lines until we encounter '{% endfor %}' that corresponds to the outer loop.
        # But there is an inner endfor and an empty block and then outer endfor.
        # Simpler: continue copying until we see a line that is exactly '{% endfor %}' and after that there is another '{% endfor %}'? That's messy.
        # Instead, let's just replace from the start of the outer for loop to the line before the outer endfor (excluding the outer endfor line) and then add the outer endfor.
        # We'll do a different approach: read entire file and use regex.
        break
    else:
        new_lines.append(line)
        i += 1

# Since the above is getting messy, let's do a regex replace on the whole content.
import re
with open('kitchendashboard.html', 'r') as f:
    content = f.read()

# Pattern from the start of the outer for loop line to just before the outer endfor line (excluding the outer endfor line).
# We'll capture the inner content and replace the whole block.
pattern = r'(\{% for table in orders|groupby:"table_session.table" %\})(\s*)<div class="bg-surface-container p-6 rounded-2xl border-2 \{% if loop\.first %}border-error ticket-urgent\{\% else \%\}border-outline-variant\{\% endif %\}">(\s*)<div class="flex justify-between items-center mb-4">(\s*)<h3 class="font-headline-md text-headline-md">Table {{ table\.grouper\.number }}</h3>(\s*)<span class="px-3 py-1 text-label-sm rounded-full\n\s*\{\% if table\.list\|first\|status == \'pending\' \%\}bg-error text-white\n\s*\{\% elif table\.list\|first\|status == \'preparing\' \%\}bg-primary text-on-primary\n\s*\{\% elif table\.list\|first\|status == \'ready\' \%\}bg-primary-container text-on-primary-container\n\s*\{\% endif %\}\}\{\{ table\.list\|first\|get_status_display \}\}</span>(\s*)</div>(\s*)'
# This is too complex due to newlines.

# Instead, let's do a simpler approach: replace the specific lines we know.
lines = content.splitlines(keepalive=True)
out = []
i = 0
while i < len(lines):
    if '{% for table in orders|groupby:"table_session.table" %}' in lines[i]:
        out.append(lines[i])
        i += 1
        # skip the div line
        i += 1  # skip <div class="bg-surface..." line
        # insert new div
        out.append('<div class="bg-surface-container p-6 rounded-2xl border-2 border-outline-variant">\n')
        # skip the flex div line
        i += 1  # skip <div class="flex justify-between items-center mb-4"> line
        # insert new flex div with h3 only
        out.append('<div class="flex justify-between items-center mb-4">\n')
        out.append('    <h3 class="font-headline-md text-headline-md">Table {{ table.grouper.number }}</h3>\n')
        out.append('</div>\n')
        # now we should be at the line that starts the inner for loop
        # copy it
        if i < len(lines):
            out.append(lines[i])
            i += 1
        # continue copying until we hit the line that is '{% endfor %}' that matches the outer loop.
        # We'll keep a counter of nested for loops.
        depth = 1  # we are inside the outer for loop
        while i < len(lines) and depth > 0:
            line = lines[i]
            if '{% for ' in line:
                depth += 1
            elif '{% endfor %}' in line:
                depth -= 1
                if depth == 0:
                    # this is the endfor for the outer loop; we will break after adding it?
                    # We'll add this line after the loop.
                    pass
            out.append(line)
            i += 1
        # after the loop, we have added the endfor line; continue.
        continue
    else:
        out.append(lines[i])
        i += 1

with open('kitchendashboard.html', 'w') as f:
    f.writelines(out)
print('Done')
