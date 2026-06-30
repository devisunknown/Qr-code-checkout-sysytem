with open('kitchendashboard.html', 'r') as f:
    content = f.read()

old = '''<div class="flex justify-between items-center mb-4">
    <h3 class="font-headline-md text-headline-md">Table {{ table.grouper.number }}</h3>
</div>'''

new = '''<div class="flex justify-between items-center mb-4">
    <h3 class="font-headline-md text-headline-md">Table {{ table.grouper.number }}</h3>
    <div>
        <form action="{% url 'mark_table_orders_ready' table.grouper.id %}" method="post" class="ml-2">
            {% csrf_token %}
            <button type="submit" class="bg-primary text-on-primary font-bold py-1 px-3 rounded-xl">Done Preparing</button>
        </form>
    </div>
</div>'''

if old in content:
    content = content.replace(old, new)
    with open('kitchendashboard.html', 'w') as f:
        f.write(content)
    print('Replaced')
else:
    print('Old snippet not found')
    # Let's print a snippet to see
    import re
    # find something similar
    pattern = r'<div class="flex justify-between items-center mb-4">.*?</div>'
    matches = re.findall(pattern, content, re.DOTALL)
    for m in matches[:5]:
        print(repr(m))
